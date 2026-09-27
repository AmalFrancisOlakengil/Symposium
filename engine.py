import json
from groq import Groq
import db

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
            max_tokens=600
        )
        reply = response.choices[0].message.content.strip()
        
        # Save agent response to DB
        db.save_message(self.group_id, persona["name"], "assistant", reply)
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
        mod_data = json.loads(result_text)
        
        # Save summary to DB log
        summary_text = f"[Moderator Summary]: {mod_data['round_summary']}"
        db.save_message(self.group_id, "Moderator", "assistant", summary_text)
        
        return mod_data


# --- CLI Proof of Concept Runner ---
if __name__ == "__main__":
    db.init_db()
    
    print("=== Welcome to Symposium CLI Proof of Concept ===")
    api_key = input("Enter Groq API Key: ").strip()
    model_id = input("Enter Groq Model ID (e.g., llama-3.3-70b-versatile): ").strip() or "llama-3.3-70b-versatile"
    
    # Set up dummy group with first 3 default personas
    all_personas = db.fetch_all_personas()
    selected_p_ids = [p["id"] for p in all_personas[:3]]  # Feasibility, Budget, Innovation
    
    group_id = db.create_chat_group("CLI Test Session", model_id, selected_p_ids)
    
    engine = SymposiumEngine(api_key, model_id, group_id)
    
    idea = input("\nEnter your initial idea to start the Symposium: ").strip()
    db.save_message(group_id, "User (Executive)", "user", idea)
    
    # CLI Turn-Taking Loop
    while True:
        print("\n--- Agents are debating... ---")
        for p in engine.personas:
            reply = engine.call_agent(p)
            print(f"\n[{p['name']}]:\n{reply}\n")
            
        print("--- Moderator Evaluating Round... ---")
        mod_info = engine.call_moderator()
        
        print("\n" + "="*50)
        print(f"📊 Consensus Reached: {mod_info.get('consensus_reached')}")
        print(f"ℹ️ Summary: {mod_info.get('round_summary')}")
        print(f"💡 Suggestion: {mod_info.get('suggested_message')}")
        print("="*50)
        
        print("\nChoose an action:")
        print("1. Continue (Next round)")
        print("2. Continue + Add Message")
        print("3. End Session")
        
        choice = input("Enter option (1/2/3): ").strip()
        
        if choice == "2":
            user_msg = input("\nEnter your message/directive: ").strip()
            db.save_message(group_id, "User (Executive)", "user", user_msg)
        elif choice == "3":
            print("\nEnding Symposium session. Goodbye!")
            break
        elif choice != "1":
            print("Invalid option, defaulting to Continue.")