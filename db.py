# db.py
import sqlite3

DB_NAME = "symposium.db"  # Updated database file name

# Core default personalities
CONVERSATIONAL_INSTRUCTION = (
    "Keep your response extremely concise, direct, and under 3-4 sentences (max 80 words). "
    "Speak casually like a team member in a quick brainstorming meeting. No long intro or outro filler."
    "Do NOT include your persona name, brackets, or prefixes (e.g. '[The Pessimist]:') in your output."
    "Respond directly in plain text with only your message content."
)

DEFAULT_PERSONAS = [
    (
        "The Feasibility Guy",
        "You are an expert systems engineer and operations manager. Focus strictly on technical viability, complexity, logistics, and practical hurdles. Be constructive but realistic." + CONVERSATIONAL_INSTRUCTION,
        0
    ),
    (
        "The Budget Guy",
        "You are a cautious CFO. Evaluate costs, infrastructure overhead, monetization potential, and resource efficiency. Keep your tone practical and financially minded." + CONVERSATIONAL_INSTRUCTION,
        0
    ),
    (
        "The Innovation Guy",
        "You are a visionary product architect. Push the boundaries of the concept. Suggest unique features, modern tech integration, and novel user experiences." + CONVERSATIONAL_INSTRUCTION,
        0
    ),
    (
        "The Pessimist",
        "You are a strict risk reviewer. Actively search for edge cases, single points of failure, market saturation, and false assumptions. Highlight weaknesses clearly." + CONVERSATIONAL_INSTRUCTION,
        0
    ),
    (
        "The Optimist",
        "You are an encouraging product strategist. Focus on high-value potential, user benefits, excitement, and opportunity areas. Inspire confidence while staying coherent." + CONVERSATIONAL_INSTRUCTION,
        0
    )
]


def get_connection():
    """Returns a connection to the SQLite database with row dict access."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables and seeds default personas if not already present."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Chat Groups
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                model_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Personas / Agents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                system_prompt TEXT NOT NULL,
                is_custom BOOLEAN DEFAULT 0
            )
        """)

        # 3. Messages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                sender_name TEXT NOT NULL,
                sender_role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
            )
        """)

        # 4. Group Members (Many-to-Many mapping)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_agents (
                group_id INTEGER NOT NULL,
                persona_id INTEGER NOT NULL,
                PRIMARY KEY (group_id, persona_id),
                FOREIGN KEY(group_id) REFERENCES chat_groups(id) ON DELETE CASCADE,
                FOREIGN KEY(persona_id) REFERENCES personas(id) ON DELETE CASCADE
            )
        """)

    

        # Seed Default Personas
        cursor.executemany("""
            INSERT OR IGNORE INTO personas (name, system_prompt, is_custom)
            VALUES (?, ?, ?)
        """, DEFAULT_PERSONAS)

        conn.commit()


# --- CRUD Helper Functions ---

def create_chat_group(title: str, model_id: str, persona_ids: list[int]) -> int:
    """Creates a new chat room and links the selected personas to it."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_groups (title, model_id) VALUES (?, ?)",
            (title, model_id)
        )
        group_id = cursor.lastrowid

        # Associate selected personas with the group
        for p_id in persona_ids:
            cursor.execute(
                "INSERT INTO group_agents (group_id, persona_id) VALUES (?, ?)",
                (group_id, p_id)
            )

        conn.commit()
        return group_id


def add_custom_persona(name: str, system_prompt: str) -> int:
    """Adds a user-defined persona agent."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO personas (name, system_prompt, is_custom) VALUES (?, ?, 1)",
            (name, system_prompt)
        )
        conn.commit()
        return cursor.lastrowid


def delete_persona(persona_id: int):
    """Deletes a persona and unbinds it from group associations."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
        conn.commit()


def delete_chat_group(group_id: int):
    """Deletes a chat group along with its messages and persona bindings."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE group_id = ?", (group_id,))
        cursor.execute("DELETE FROM group_agents WHERE group_id = ?", (group_id,))
        cursor.execute("DELETE FROM chat_groups WHERE id = ?", (group_id,))
        conn.commit()


def fetch_all_personas() -> list[dict]:
    """Retrieves all default and custom personas."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM personas ORDER BY is_custom ASC, name ASC")
        return [dict(row) for row in cursor.fetchall()]


def fetch_group_personas(group_id: int) -> list[dict]:
    """Fetches all active personas configured for a given chat group."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.* FROM personas p
            JOIN group_agents ga ON p.id = ga.persona_id
            WHERE ga.group_id = ?
        """, (group_id,))
        return [dict(row) for row in cursor.fetchall()]

def fetch_all_groups() -> list[dict]:
    """Retrieves all chat groups ordered by creation time (newest first)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, model_id, created_at 
            FROM chat_groups 
            ORDER BY id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def save_message(group_id: int, sender_name: str, sender_role: str, content: str) -> int:
    """Saves a single message (User, Agent, or Moderator) to the chat log."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (group_id, sender_name, sender_role, content)
            VALUES (?, ?, ?, ?)
        """, (group_id, sender_name, sender_role, content))
        conn.commit()
        return cursor.lastrowid


def fetch_messages(group_id: int) -> list[dict]:
    """Retrieves the full message transcript for a chat group."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sender_name, sender_role, content, timestamp 
            FROM messages 
            WHERE group_id = ? 
            ORDER BY id ASC
        """, (group_id,))
        return [dict(row) for row in cursor.fetchall()]


if __name__ == "__main__":
    # Sanity check run
    init_db()
    print("Database schema initialized successfully.")
    personas = fetch_all_personas()
    print(f"Loaded {len(personas)} personas:")
    for p in personas:
        print(f" - [{p['id']}] {p['name']} (Custom: {bool(p['is_custom'])})")