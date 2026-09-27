import threading
from typing import Callable, Optional
import db
from engine import SymposiumEngine


class SymposiumSessionRunner:
    """
    Manages the background execution loop for a Symposium brainstorming session.
    Communicates back to the UI via thread-safe callbacks.
    """

    def __init__(
        self,
        api_key: str,
        model_id: str,
        group_id: int,
        ui_callback: Callable[[dict], None]
    ):
        self.engine = SymposiumEngine(api_key, model_id, group_id)
        self.group_id = group_id
        self.ui_callback = ui_callback

        # Threading & Control Flags
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        
        # Event used to pause the background thread waiting for human input
        self.user_action_event = threading.Event()
        
        # User decision state passed from UI
        self.pending_action: Optional[str] = None  # 'continue', 'continue_with_msg', or 'end'
        self.pending_message: Optional[str] = None

    def start_session(self):
        """Starts the background thread worker."""
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop_session(self):
        """Stops the loop and unblocks waiting events."""
        self.is_running = False
        self.user_action_event.set()

    def submit_user_action(self, action: str, message: Optional[str] = None):
        """
        Called by UI button handlers to unblock the waiting background thread.
        
        :param action: 'continue', 'continue_with_msg', or 'end'
        :param message: User directive text if action is 'continue_with_msg'
        """
        self.pending_action = action
        self.pending_message = message

        if action == "continue_with_msg" and message:
            db.save_message(self.group_id, "User (Executive)", "user", message)
        elif action == "continue":
            db.save_message(
                self.group_id, 
                "User (Executive)", 
                "user", 
                "Proceed to next turn without additional instructions."
            )

        # Unblock the background loop
        self.user_action_event.set()

    def _run_loop(self):
        """Main execution loop running in a background thread."""
        while self.is_running:
            # 1. Sequential turn for each active agent in the room
            for persona in self.engine.personas:
                if not self.is_running:
                    break

                # Notify UI that agent is generating
                self.ui_callback({
                    "type": "AGENT_THINKING",
                    "sender": persona["name"]
                })

                # Call Groq API
                reply = self.engine.call_agent(persona)

                # Send new message to UI
                self.ui_callback({
                    "type": "NEW_MESSAGE",
                    "sender": persona["name"],
                    "sender_role": "assistant",
                    "content": reply
                })

            if not self.is_running:
                break

            # 2. Call Moderator to check consensus and summarize round
            self.ui_callback({"type": "MODERATOR_THINKING"})
            mod_data = self.engine.call_moderator()

            # 3. Trigger UI Prompt Gate (Displays choices & consensus info)
            self.ui_callback({
                "type": "PROMPT_GATE",
                "consensus_reached": mod_data.get("consensus_reached", False),
                "round_summary": mod_data.get("round_summary", ""),
                "suggested_message": mod_data.get("suggested_message", "")
            })

            # 4. PAUSE THREAD: Wait until user clicks a button in the UI
            self.user_action_event.clear()
            self.user_action_event.wait()

            # Handle user choice
            if self.pending_action == "end" or not self.is_running:
                self.is_running = False
                self.ui_callback({
                    "type": "SESSION_ENDED",
                    "summary": mod_data.get("round_summary", "Session terminated by user.")
                })
                break


# --- Thread Test Runner ---
if __name__ == "__main__":
    import time

    def mock_ui_callback(event: dict):
        """Simulates how the CustomTkinter GUI will receive events from the thread."""
        event_type = event["type"]
        if event_type == "AGENT_THINKING":
            print(f"⏳ [{event['sender']}] is typing...")
        elif event_type == "NEW_MESSAGE":
            print(f"\n💬 [{event['sender']}]: {event['content']}\n")
        elif event_type == "MODERATOR_THINKING":
            print("⏳ Moderator is evaluating the round...")
        elif event_type == "PROMPT_GATE":
            print("\n" + "="*50)
            print(f"📊 Consensus Reached: {event['consensus_reached']}")
            print(f"ℹ️ Summary: {event['round_summary']}")
            print(f"💡 Suggestion: {event['suggested_message']}")
            print("="*50)

    # Initialize DB & prompt for dynamic user inputs
    db.init_db()
    personas = db.fetch_all_personas()
    p_ids = [p["id"] for p in personas[:2]]  # Pick 2 personas for quick testing
    
    api_key = input("Enter Groq API Key: ").strip()
    model_id = input("Enter Groq Model ID (e.g., llama-3.3-70b-versatile): ").strip() or "llama-3.3-70b-versatile"
    
    group_id = db.create_chat_group("Thread Test Group", model_id, p_ids)
    
    initial_idea = input("Enter initial idea to start session: ").strip() or "How can we reduce application latency?"
    db.save_message(group_id, "User (Executive)", "user", initial_idea)

    runner = SymposiumSessionRunner(api_key, model_id, group_id, mock_ui_callback)
    
    print("\nStarting background session thread...")
    runner.start_session()

    # Simulate UI pausing for 10 seconds after round 1, then sending 'end'
    time.sleep(10)
    print("\n[Simulated UI]: User clicks 'End Session'...")
    runner.submit_user_action("end")
    time.sleep(1)
    print("Thread test completed.")