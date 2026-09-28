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
                try:
                    reply = self.engine.call_agent(persona)

                    # Send new message to UI
                    self.ui_callback({
                        "type": "NEW_MESSAGE",
                        "sender": persona["name"],
                        "sender_role": "assistant",
                        "content": reply
                    })
                except:
                    self.is_running = False
                    self.ui_callback({
                                                       "type": "SESSION_ENDED",
                                                       "summary": "An Error Occurred to your Groq API call \n Possible reasons: \n 1) Invalid API key\n2) Invalid Model ID\n 3) Rate Limit reached"
                    })
                    break

            if not self.is_running:
                break

            # 2. Call Moderator to check consensus and summarize round
            self.ui_callback({"type": "MODERATOR_THINKING"})
            try:
                mod_data = self.engine.call_moderator()

                # 3. Trigger UI Prompt Gate (Displays choices & consensus info)
                self.ui_callback({
                    "type": "PROMPT_GATE",
                    "consensus_reached": mod_data.get("consensus_reached", False),
                    "round_summary": mod_data.get("round_summary", ""),
                    "suggested_message": mod_data.get("suggested_message", "")
                })
            except:
                self.is_running = False
                self.ui_callback({
                                   "type": "SESSION_ENDED",
                                   "summary": "An Error Occurred to your Groq API call \n Possible reasons: \n 1) Invalid API key\n2) Invalid Model ID\n 3) Rate Limit reached"
                })
                break


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

