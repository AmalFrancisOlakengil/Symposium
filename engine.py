import json
from groq import Groq
import db
import re

MODERATOR_SYSTEM_PROMPT = """
You are the Discussion Moderator for 'Symposium', an AI product brainstorming app.
Your task is to analyze the conversation history and do TWO things:

1. Evaluate if consensus has been reached among the agents regarding the proposed idea.
2. Generate a concise summary of the current stance and a suggested message/question for the user.

You MUST respond ONLY with valid JSON matching this schema:
{
  "consensus_reached": boolean,
  "round_summary": "Brief 1-2 sentence summary of key points discussed or remaining debate points.",
  "suggested_message": "A guiding question or suggestion for the user if they want to steer the debate."
}
"""
def clean_agent_response(persona_name: str, raw_text: str) -> str:
    """Strips recursive speaker prefixes like '[The Pessimist]:' or 'The Pessimist:'."""
    # Pattern matches standard brackets [Name]: or plain Name: at the start
    pattern = r"^(?:\[?[A-Za-z0-9_\s\-\(\)]+\]?:\s*)+"
    cleaned = re.sub(pattern, "", raw_text.strip()).strip()
    return cleaned

class SymposiumEngine:
    def __init__(self, api_key: str, model_id: str, group_id: int):
        self.client = Groq(api_key=api_key)
        self.model_id = model_id
        self.group_id = group_id
        
        # Load agents assigned to this group from SQLite
        self.personas = db.fetch_group_personas(group_id)

    def _get_chat_history(self) -> list[dict]:
        """Fetch and format previous messages for API calls."""
        raw_messages = db.fetch_messages(self.group_id)
        formatted = []
        for msg in raw_messages:
            formatted.append({
                "sender": msg["sender_name"],
                "role": msg["sender_role"],
                "content": msg["content"]
            })
        return formatted

    def call_agent(self, persona: dict) -> str:
        """Call a specific persona agent using Groq API."""
        history = self._get_chat_history()
        
        system_prompt = f"You are {persona['name']}. {persona['system_prompt']}"
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in history:
            prefix = f"[{msg['sender']}]: " if msg['role'] != 'system' else ""
            messages.append({"role": msg['role'], "content": f"{prefix}{msg['content']}"})

        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            temperature=0.7,
            max_tokens=120
        )
        reply = response.choices[0].message.content.strip()
        cleaned_text = clean_agent_response(persona['name'], reply)
        
        # Save agent response to DB
        db.save_message(self.group_id, persona["name"], "assistant", cleaned_text)
        return reply

    def call_moderator(self) -> dict:
        """Ask Moderator to evaluate consensus and summarize round."""
        history = self._get_chat_history()
        history_str = "\n".join([f"{m['sender']}: {m['content']}" for m in history])

        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": MODERATOR_SYSTEM_PROMPT},
                {"role": "user", "content": f"Conversation History:\n{history_str}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )
        
        result_text = response.choices[0].message.content.strip()
        cleaned_text = clean_agent_response("Moderator", result_text)
        mod_data = json.loads(cleaned_text)
        
        # Save summary to DB log
        summary_text = f"[Moderator Summary]: {mod_data['round_summary']}"
        db.save_message(self.group_id, "Moderator", "assistant", summary_text)
        
        return mod_data



