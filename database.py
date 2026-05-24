from __future__ import annotations
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / 'weight_rewards.db'

DEFAULT_THRESHOLDS = [
    {'label': 'Below 220 lb', 'target_weight': 220.5, 'reward_amount': 10.0},
    {'label': 'Below 209 lb', 'target_weight': 209.4, 'reward_amount': 15.0},
    {'label': 'Below 198 lb', 'target_weight': 198.4, 'reward_amount': 25.0},
    {'label': 'Below 187 lb', 'target_weight': 187.4, 'reward_amount': 40.0},
    {'label': 'Below 176 lb', 'target_weight': 176.4, 'reward_amount': 60.0},
]

DEFAULT_REWARD_ITEMS = [
    {
        'name': 'Protein bar pack',
        'price': 4.0,
        'link': 'https://example.com/protein-bars',
    },
    {
        'name': 'Fitness class pass',
        'price': 20.0,
        'link': 'https://example.com/fitness-pass',
    },
    {
        'name': 'Healthy recipe book',
        'price': 12.0,
        'link': 'https://example.com/healthy-recipes',
    },
    {
        'name': 'New workout shirt',
        'price': 18.0,
        'link': 'https://example.com/workout-shirt',
    },
    {
        'name': 'Massage session',
        'price': 35.0,
        'link': 'https://example.com/massage-session',
    },
    {
        'name': 'Sport headphones',
        'price': 45.0,
        'link': 'https://example.com/sport-headphones',
    },
]

class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        with self.conn:
            self.conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS week_weights (
                    id INTEGER PRIMARY KEY,
                    entry_date TEXT NOT NULL UNIQUE,
                    weight REAL NOT NULL
                )
                '''
            )
            self.conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS reward_thresholds (
                    id INTEGER PRIMARY KEY,
                    label TEXT NOT NULL,
                    target_weight REAL NOT NULL,
                    reward_amount REAL NOT NULL,
                    reached INTEGER NOT NULL DEFAULT 0
                )
                '''
            )
            self.conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS reward_items (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    link TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1
                )
                '''
            )
            self.conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS reward_claims (
                    id INTEGER PRIMARY KEY,
                    threshold_id INTEGER NOT NULL,
                    claimed_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    FOREIGN KEY(threshold_id) REFERENCES reward_thresholds(id)
                )
                '''
            )
            self.conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS reward_claim_items (
                    claim_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    FOREIGN KEY(claim_id) REFERENCES reward_claims(id),
                    FOREIGN KEY(item_id) REFERENCES reward_items(id)
                )
                '''
            )
            self._migrate_schema()
            self._seed_thresholds()
            self._seed_reward_items()

    def _migrate_schema(self) -> None:
        item_columns = {row['name'] for row in self.conn.execute("PRAGMA table_info(reward_items)").fetchall()}
        if 'link' not in item_columns:
            self.conn.execute('ALTER TABLE reward_items ADD COLUMN link TEXT NOT NULL DEFAULT ""')
        if 'active' not in item_columns:
            self.conn.execute('ALTER TABLE reward_items ADD COLUMN active INTEGER NOT NULL DEFAULT 1')

        claim_columns = {row['name'] for row in self.conn.execute("PRAGMA table_info(reward_claims)").fetchall()}
        if 'status' not in claim_columns:
            self.conn.execute('ALTER TABLE reward_claims ADD COLUMN status TEXT NOT NULL DEFAULT "draft"')
            self.conn.execute("UPDATE reward_claims SET status = 'claimed' WHERE status IS NULL OR status = ''")

        self.conn.execute(
            '''
            DELETE FROM reward_thresholds
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM reward_thresholds
                GROUP BY label
            )
            '''
        )
        self.conn.execute(
            '''
            DELETE FROM reward_items
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM reward_items
                GROUP BY name
            )
            '''
        )
        self.conn.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_reward_thresholds_label ON reward_thresholds(label)'
        )
        self.conn.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_reward_items_name ON reward_items(name)'
        )
        # ensure image column exists
        item_columns = {row['name'] for row in self.conn.execute("PRAGMA table_info(reward_items)").fetchall()}
        if 'image' not in item_columns:
            try:
                self.conn.execute('ALTER TABLE reward_items ADD COLUMN image TEXT NOT NULL DEFAULT ""')
            except Exception:
                pass

    def _seed_thresholds(self) -> None:
        existing = self.conn.execute('SELECT COUNT(*) FROM reward_thresholds').fetchone()[0]
        if existing == 0:
            for threshold in DEFAULT_THRESHOLDS:
                self.conn.execute(
                    '''
                    INSERT INTO reward_thresholds (label, target_weight, reward_amount)
                    VALUES (?, ?, ?)
                    ''',
                    (threshold['label'], threshold['target_weight'], threshold['reward_amount']),
                )

    def _seed_reward_items(self) -> None:
        existing = self.conn.execute('SELECT COUNT(*) FROM reward_items').fetchone()[0]
        if existing == 0:
            for item in DEFAULT_REWARD_ITEMS:
                self.conn.execute(
                    '''
                    INSERT INTO reward_items (name, price, link)
                    VALUES (?, ?, ?)
                    ''',
                    (item['name'], item['price'], item['link']),
                )

    def add_weight_entry(self, entry_date: date, weight: float) -> None:
        with self.conn:
            self.conn.execute(
                '''
                INSERT INTO week_weights (entry_date, weight)
                VALUES (?, ?)
                ON CONFLICT(entry_date) DO UPDATE SET weight = excluded.weight
                ''',
                (entry_date.isoformat(), weight),
            )

    def get_recent_weights(self, limit: int = 20) -> List[Dict[str, object]]:
        rows = self.conn.execute(
            '''
            SELECT entry_date, weight
            FROM week_weights
            ORDER BY entry_date DESC
            LIMIT ?
            ''',
            (limit,),
        ).fetchall()
        return [
            {'date': date.fromisoformat(row['entry_date']), 'weight': row['weight']}
            for row in rows
        ]

    def get_weight_for_date(self, entry_date: date) -> Optional[float]:
        row = self.conn.execute(
            '''
            SELECT weight FROM week_weights WHERE entry_date = ?
            ''',
            (entry_date.isoformat(),),
        ).fetchone()
        if not row:
            return None
        return row['weight']

    def get_saturday_weights(self) -> List[Dict[str, object]]:
        rows = self.conn.execute(
            '''
            SELECT entry_date, weight
            FROM week_weights
            ORDER BY entry_date ASC
            ''',
        ).fetchall()
        return [
            {'date': entry_date, 'weight': row['weight']}
            for row in rows
            if (entry_date := date.fromisoformat(row['entry_date'])).weekday() == 5
        ]

    def get_last_two_saturday_weights(self) -> List[Dict[str, object]]:
        saturday_weights = self.get_saturday_weights()
        return saturday_weights[-2:]

    def get_thresholds(self) -> List[Dict[str, object]]:
        rows = self.conn.execute(
            '''
            SELECT id, label, target_weight, reward_amount, reached
            FROM reward_thresholds
            WHERE label NOT LIKE '%kg%'
            ORDER BY target_weight ASC
            ''',
        ).fetchall()
        return [
            {
                'id': row['id'],
                'label': row['label'],
                'target_weight': row['target_weight'],
                'reward_amount': row['reward_amount'],
                'reached': bool(row['reached']),
            }
            for row in rows
        ]

    def get_reward_items(self, active_only: bool = True) -> List[Dict[str, object]]:
        query = '''
            SELECT id, name, price, link, active, image
            FROM reward_items
        '''
        if active_only:
            query += ' WHERE active = 1'
        query += ' ORDER BY price ASC, name ASC'
        rows = self.conn.execute(query).fetchall()
        return [
            {
                'id': row['id'],
                'name': row['name'],
                'price': row['price'],
                'link': row['link'],
                'active': bool(row['active']),
                'image': row['image'],
            }
            for row in rows
        ]

    def get_eligible_threshold(self) -> Optional[Dict[str, object]]:
        weights = self.get_last_two_saturday_weights()
        if len(weights) < 2:
            return None
        for threshold in self.get_thresholds():
            if threshold['reached']:
                continue
            if all(entry['weight'] <= threshold['target_weight'] for entry in weights):
                return threshold
        return None

    def remove_reward_item(self, item_id: int) -> None:
        with self.conn:
            # remove any claim items referencing this item
            self.conn.execute('DELETE FROM reward_claim_items WHERE item_id = ?', (item_id,))
            self.conn.execute('DELETE FROM reward_items WHERE id = ?', (item_id,))

    def remove_threshold(self, threshold_id: int) -> None:
        with self.conn:
            # delete associated claims and claim items first
            claim_ids = [r['id'] for r in self.conn.execute('SELECT id FROM reward_claims WHERE threshold_id = ?', (threshold_id,)).fetchall()]
            for cid in claim_ids:
                self.conn.execute('DELETE FROM reward_claim_items WHERE claim_id = ?', (cid,))
            self.conn.execute('DELETE FROM reward_claims WHERE threshold_id = ?', (threshold_id,))
            self.conn.execute('DELETE FROM reward_thresholds WHERE id = ?', (threshold_id,))

    def get_next_unreached_threshold(self) -> Optional[Dict[str, object]]:
        thresholds = [t for t in self.get_thresholds() if not t['reached']]
        if not thresholds:
            return None
        return thresholds[-1]

    def claim_reward(self, threshold_id: int, item_ids: List[int]) -> None:
        self.finalize_reward_claim(threshold_id, item_ids)

    def save_reward_selection(self, threshold_id: int, item_ids: List[int]) -> None:
        with self.conn:
            draft = self.conn.execute(
                '''
                SELECT id FROM reward_claims
                WHERE threshold_id = ? AND status = 'draft'
                ''',
                (threshold_id,),
            ).fetchone()
            if draft:
                claim_id = draft['id']
                self.conn.execute(
                    '''
                    UPDATE reward_claims
                    SET claimed_at = ?, status = 'draft'
                    WHERE id = ?
                    ''',
                    (date.today().isoformat(), claim_id),
                )
                self.conn.execute(
                    'DELETE FROM reward_claim_items WHERE claim_id = ?',
                    (claim_id,),
                )
            else:
                cursor = self.conn.execute(
                    '''
                    INSERT INTO reward_claims (threshold_id, claimed_at, status)
                    VALUES (?, ?, 'draft')
                    ''',
                    (threshold_id, date.today().isoformat()),
                )
                claim_id = cursor.lastrowid
            for item_id in item_ids:
                self.conn.execute(
                    '''
                    INSERT INTO reward_claim_items (claim_id, item_id)
                    VALUES (?, ?)
                    ''',
                    (claim_id, item_id),
                )

    def finalize_reward_claim(self, threshold_id: int, item_ids: List[int]) -> None:
        with self.conn:
            draft = self.conn.execute(
                '''
                SELECT id FROM reward_claims
                WHERE threshold_id = ? AND status = 'draft'
                ''',
                (threshold_id,),
            ).fetchone()
            if draft:
                claim_id = draft['id']
                self.conn.execute(
                    '''
                    UPDATE reward_claims
                    SET claimed_at = ?, status = 'claimed'
                    WHERE id = ?
                    ''',
                    (date.today().isoformat(), claim_id),
                )
                self.conn.execute('DELETE FROM reward_claim_items WHERE claim_id = ?', (claim_id,))
            else:
                cursor = self.conn.execute(
                    '''
                    INSERT INTO reward_claims (threshold_id, claimed_at, status)
                    VALUES (?, ?, 'claimed')
                    ''',
                    (threshold_id, date.today().isoformat()),
                )
                claim_id = cursor.lastrowid

            for item_id in item_ids:
                self.conn.execute(
                    '''
                    INSERT INTO reward_claim_items (claim_id, item_id)
                    VALUES (?, ?)
                    ''',
                    (claim_id, item_id),
                )
            self.conn.execute(
                '''
                UPDATE reward_thresholds
                SET reached = 1
                WHERE id = ?
                ''',
                (threshold_id,),
            )
            if item_ids:
                self.conn.execute(
                    f"UPDATE reward_items SET active = 0 WHERE id IN ({','.join(['?'] * len(item_ids))})",
                    item_ids,
                )

    def get_draft_claim(self, threshold_id: int) -> Optional[Dict[str, object]]:
        row = self.conn.execute(
            '''
            SELECT id, claimed_at, status
            FROM reward_claims
            WHERE threshold_id = ? AND status = 'draft'
            ''',
            (threshold_id,),
        ).fetchone()
        if not row:
            return None
        item_rows = self.conn.execute(
            '''
            SELECT item_id FROM reward_claim_items
            WHERE claim_id = ?
            ''',
            (row['id'],),
        ).fetchall()
        return {
            'claim_id': row['id'],
            'threshold_id': threshold_id,
            'status': row['status'],
            'item_ids': [item['item_id'] for item in item_rows],
        }

    def get_pending_claims(self) -> List[Dict[str, object]]:
        rows = self.conn.execute(
            '''
            SELECT c.id, c.threshold_id, c.claimed_at, t.label, t.reward_amount
            FROM reward_claims AS c
            JOIN reward_thresholds AS t ON c.threshold_id = t.id
            WHERE c.status = 'draft'
            ORDER BY c.claimed_at DESC
            ''',
        ).fetchall()
        claims = []
        for row in rows:
            item_rows = self.conn.execute(
                '''
                SELECT ri.name, ri.price, ri.link
                FROM reward_claim_items AS ci
                JOIN reward_items AS ri ON ci.item_id = ri.id
                WHERE ci.claim_id = ?
                ''',
                (row['id'],),
            ).fetchall()
            claims.append(
                {
                    'claim_id': row['id'],
                    'threshold_id': row['threshold_id'],
                    'threshold_label': row['label'],
                    'reward_amount': row['reward_amount'],
                    'claimed_at': row['claimed_at'],
                    'status': 'draft',
                    'items': [
                        {'name': item['name'], 'price': item['price'], 'link': item['link']}
                        for item in item_rows
                    ],
                }
            )
        return claims

    def delete_draft_claim(self, claim_id: int) -> None:
        with self.conn:
            self.conn.execute('DELETE FROM reward_claim_items WHERE claim_id = ?', (claim_id,))
            self.conn.execute('DELETE FROM reward_claims WHERE id = ?', (claim_id,))

    def get_claims(self) -> List[Dict[str, object]]:
        rows = self.conn.execute(
            '''
            SELECT c.id, c.threshold_id, c.claimed_at, c.status, t.label, t.reward_amount
            FROM reward_claims AS c
            JOIN reward_thresholds AS t ON c.threshold_id = t.id
            ORDER BY c.claimed_at DESC
            ''',
        ).fetchall()
        claims = []
        for row in rows:
            item_rows = self.conn.execute(
                '''
                SELECT ri.name, ri.price, ri.link
                FROM reward_claim_items AS ci
                JOIN reward_items AS ri ON ci.item_id = ri.id
                WHERE ci.claim_id = ?
                ''',
                (row['id'],),
            ).fetchall()
            claims.append(
                {
                    'claim_id': row['id'],
                    'threshold_label': row['label'],
                    'reward_amount': row['reward_amount'],
                    'claimed_at': row['claimed_at'],
                    'status': row['status'],
                    'items': [
                        {
                            'name': item['name'],
                            'price': item['price'],
                            'link': item['link'],
                        }
                        for item in item_rows
                    ],
                }
            )
        return claims

    def add_reward_item(self, name: str, price: float, link: str = '', image: str = '') -> None:
        with self.conn:
            self.conn.execute(
                '''
                INSERT INTO reward_items (name, price, link, image)
                VALUES (?, ?, ?, ?)
                ''',
                (name, price, link, image),
            )

    def remove_weight_entry(self, entry_date: date) -> None:
        with self.conn:
            self.conn.execute(
                'DELETE FROM week_weights WHERE entry_date = ?',
                (entry_date.isoformat(),),
            )

    def add_threshold(self, label: str, target_weight: float, reward_amount: float) -> None:
        with self.conn:
            self.conn.execute(
                '''
                INSERT INTO reward_thresholds (label, target_weight, reward_amount)
                VALUES (?, ?, ?)
                ''',
                (label, target_weight, reward_amount),
            )

    def update_threshold(self, threshold_id: int, label: str, target_weight: float, reward_amount: float) -> None:
        with self.conn:
            self.conn.execute(
                '''
                UPDATE reward_thresholds
                SET label = ?, target_weight = ?, reward_amount = ?
                WHERE id = ?
                ''',
                (label, target_weight, reward_amount, threshold_id),
            )

    def update_reward_item(self, item_id: int, name: str, price: float, link: str, image: str) -> None:
        with self.conn:
            self.conn.execute(
                '''
                UPDATE reward_items
                SET name = ?, price = ?, link = ?, image = ?
                WHERE id = ?
                ''',
                (name, price, link, image, item_id),
            )

    def calculate_weight_trend(self, lookback: int = 4) -> Optional[float]:
        weights = self.get_saturday_weights()
        if len(weights) < 2:
            return None
        recent = weights[-lookback:]
        if len(recent) < 2:
            return None
        total_change = recent[-1]['weight'] - recent[0]['weight']
        total_weeks = len(recent) - 1
        return total_change / total_weeks if total_weeks else None

