import queue
import customtkinter as ctk
import db
from session_runner import SymposiumSessionRunner

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class SymposiumApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Symposium - Multi-Agent Brainstorming Suite")
        self.geometry("1150 x 780")
        self.minsize(950, 650)

        # State Variables
        self.runner = None
        self.event_queue = queue.Queue()
        self.current_group_id = None
        self.persona_checkboxes = {}

        # Build UI
        self._init_layout()
        self._load_initial_data()

        # Start thread-safe queue polling loop
        self.after(100, self._process_queue)

    def _init_layout(self):
        """Construct layout: Sidebar with Configs/Past Sessions + Chat Area."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- LEFT SIDEBAR ---
        self.sidebar = ctk.CTkScrollableFrame(self, width=320, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # Title
        ctk.CTkLabel(
            self.sidebar, text="SYMPOSIUM", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        # API Key Entry
        ctk.CTkLabel(self.sidebar, text="Groq API Key:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=15, pady=(5, 2))
        self.api_key_entry = ctk.CTkEntry(self.sidebar, placeholder_text="gsk_...", show="*")
        self.api_key_entry.pack(fill="x", padx=15, pady=(0, 10))

        # Model Entry Field
        ctk.CTkLabel(self.sidebar, text="Model ID:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=15, pady=(5, 2))
        self.model_entry = ctk.CTkEntry(self.sidebar, placeholder_text="e.g. llama-3.3-70b-versatile")
        self.model_entry.insert(0, "llama-3.3-70b-versatile")
        self.model_entry.pack(fill="x", padx=15, pady=(0, 10))

        # Session Title
        ctk.CTkLabel(self.sidebar, text="Session Title:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=15, pady=(5, 2))
        self.session_title_entry = ctk.CTkEntry(self.sidebar, placeholder_text="e.g., Latency Optimization")
        self.session_title_entry.pack(fill="x", padx=15, pady=(0, 10))

        # --- PERSONA MANAGEMENT SECTION ---
        ctk.CTkLabel(
            self.sidebar, text="Participating Agents:", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.persona_frame = ctk.CTkFrame(self.sidebar)
        self.persona_frame.pack(fill="x", padx=15, pady=5)

        # Custom Persona Toggle / Expandable Form
        self.add_persona_btn = ctk.CTkButton(
            self.sidebar, text="+ Add Custom Persona", fg_color="transparent", border_width=1, command=self._toggle_custom_persona_form
        )
        self.add_persona_btn.pack(fill="x", padx=15, pady=(5, 10))

        self.custom_persona_frame = ctk.CTkFrame(self.sidebar)
        self.custom_name_entry = ctk.CTkEntry(self.custom_persona_frame, placeholder_text="Persona Name")
        self.custom_name_entry.pack(fill="x", padx=10, pady=4)
        
        self.custom_prompt_entry = ctk.CTkTextbox(self.custom_persona_frame, height=80, wrap="word")
        self.custom_prompt_entry.pack(fill="x", padx=10, pady=4)
        self.custom_prompt_entry.insert("1.0", "Enter system prompt/instructions...")

        ctk.CTkButton(self.custom_persona_frame, text="Save Persona", command=self._save_custom_persona).pack(fill="x", padx=10, pady=(4, 8))

        # --- PAST SESSIONS SECTION ---
        ctk.CTkLabel(
            self.sidebar, text="Past Discussions:", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))

        self.past_groups_frame = ctk.CTkFrame(self.sidebar)
        self.past_groups_frame.pack(fill="x", padx=15, pady=5)

        # --- RIGHT MAIN CHAT AREA ---
        self.main_chat_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_chat_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.main_chat_frame.grid_rowconfigure(0, weight=1)
        self.main_chat_frame.grid_columnconfigure(0, weight=1)

        # Scrollable Chat Display
        self.chat_display = ctk.CTkScrollableFrame(self.main_chat_frame)
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 10))
        self.chat_display.grid_columnconfigure(0, weight=1)

        # Status Bar
        self.status_label = ctk.CTkLabel(
            self.main_chat_frame, text="Ready to start or view session.", font=ctk.CTkFont(size=12, slant="italic"), anchor="w"
        )
        self.status_label.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))

        # Bottom Interaction Panel
        self.controls_frame = ctk.CTkFrame(self.main_chat_frame)
        self.controls_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        self.controls_frame.grid_columnconfigure(0, weight=1)

        self.user_input_entry = ctk.CTkEntry(
            self.controls_frame, placeholder_text="Type initial prompt or executive instruction..."
        )
        self.user_input_entry.grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 5), sticky="ew")

        self.start_btn = ctk.CTkButton(self.controls_frame, text="Start Session", command=self.start_session)
        self.start_btn.grid(row=1, column=0, padx=10, pady=10, sticky="ew")

        self.continue_btn = ctk.CTkButton(
            self.controls_frame, text="Continue Round", state="disabled", fg_color="gray", command=self.on_continue
        )
        self.continue_btn.grid(row=1, column=1, padx=5, pady=10, sticky="ew")

        self.end_btn = ctk.CTkButton(
            self.controls_frame,
            text="End Session",
            state="disabled",
            fg_color="transparent",
            border_color="red",
            border_width=1,
            text_color="red",
            command=self.on_end_session,
        )
        self.end_btn.grid(row=1, column=2, padx=10, pady=10, sticky="ew")

    def _load_initial_data(self):
        """Populate database defaults, personas, and past session history."""
        db.init_db()
        self._refresh_personas()
        self._refresh_past_groups()

    def _refresh_personas(self):
        """Re-render persona list in sidebar with delete options."""
        for widget in self.persona_frame.winfo_children():
            widget.destroy()

        self.persona_checkboxes.clear()
        personas = db.fetch_all_personas()

        for persona in personas:
            p_row = ctk.CTkFrame(self.persona_frame, fg_color="transparent")
            p_row.pack(fill="x", pady=2, padx=2)
            p_row.grid_columnconfigure(0, weight=1)

            var = ctk.BooleanVar(value=True)
            chk = ctk.CTkCheckBox(p_row, text=f"{persona['name']}", variable=var)
            chk.grid(row=0, column=0, sticky="w", padx=2)
            self.persona_checkboxes[persona["id"]] = (chk, var)

            # Delete button for persona
            del_btn = ctk.CTkButton(
                p_row,
                text="✕",
                width=24,
                height=24,
                fg_color="transparent",
                text_color="gray",
                hover_color="#552222",
                command=lambda p_id=persona["id"]: self._delete_persona(p_id)
            )
            del_btn.grid(row=0, column=1, sticky="e", padx=2)

    def _refresh_past_groups(self):
        """Re-render past chat groups in sidebar with delete options."""
        for widget in self.past_groups_frame.winfo_children():
            widget.destroy()

        groups = db.fetch_all_groups()
        if not groups:
            ctk.CTkLabel(self.past_groups_frame, text="No previous discussions.", font=ctk.CTkFont(size=11, slant="italic")).pack(padx=5, pady=5)
            return

        for group in groups:
            btn_frame = ctk.CTkFrame(self.past_groups_frame, fg_color="transparent")
            btn_frame.pack(fill="x", pady=2)
            btn_frame.grid_columnconfigure(0, weight=1)

            btn = ctk.CTkButton(
                btn_frame,
                text=f"📁 {group['title']}",
                fg_color="transparent",
                anchor="w",
                command=lambda g_id=group["id"]: self.load_past_group(g_id)
            )
            btn.grid(row=0, column=0, sticky="ew", padx=(2, 2))

            # Delete button for group
            del_btn = ctk.CTkButton(
                btn_frame,
                text="✕",
                width=24,
                height=24,
                fg_color="transparent",
                text_color="gray",
                hover_color="#552222",
                command=lambda g_id=group["id"]: self._delete_group(g_id)
            )
            del_btn.grid(row=0, column=1, sticky="e", padx=2)

    def _toggle_custom_persona_form(self):
        """Expands or collapses custom persona creation form."""
        if self.custom_persona_frame.winfo_ismapped():
            self.custom_persona_frame.pack_forget()
        else:
            self.custom_persona_frame.pack(fill="x", padx=15, pady=5, after=self.add_persona_btn)

    def _save_custom_persona(self):
        """Saves custom persona using (name, system_prompt)."""
        name = self.custom_name_entry.get().strip()
        prompt = self.custom_prompt_entry.get("1.0", "end").strip()

        if not name or not prompt or prompt == "Enter system prompt/instructions...":
            self.status_label.configure(text="⚠️ Custom Persona requires a Name and System Prompt.")
            return

        db.add_custom_persona(name, prompt)
        
        # Clear inputs and hide form
        self.custom_name_entry.delete(0, "end")
        self.custom_prompt_entry.delete("1.0", "end")
        self.custom_persona_frame.pack_forget()

        # Refresh persona list
        self._refresh_personas()
        self.status_label.configure(text=f"✅ Saved custom persona '{name}'.")

    def _delete_persona(self, persona_id: int):
        """Deletes a persona from DB and updates UI."""
        db.delete_persona(persona_id)
        self._refresh_personas()
        self.status_label.configure(text="🗑️ Persona deleted.")

    def _delete_group(self, group_id: int):
        """Deletes a chat group from DB and updates UI."""
        db.delete_chat_group(group_id)
        if self.current_group_id == group_id:
            for widget in self.chat_display.winfo_children():
                widget.destroy()
            self.current_group_id = None

        self._refresh_past_groups()
        self.status_label.configure(text="🗑️ Discussion deleted.")

    def load_past_group(self, group_id: int):
        """Loads and displays history of a past session in the chat viewer."""
        for widget in self.chat_display.winfo_children():
            widget.destroy()

        self.current_group_id = group_id
        messages = db.fetch_messages(group_id)

        for msg in messages:
            is_summary = msg["sender_name"] == "Moderator"
            self._append_chat_message(
                sender=msg["sender_name"],
                role=msg["sender_role"],
                content=msg["content"],
                is_summary=is_summary
            )

        self.status_label.configure(text=f"📜 Loaded past discussion (Group ID #{group_id}).")

    def _thread_callback(self, event: dict):
        self.event_queue.put(event)

    def _process_queue(self):
        try:
            while True:
                event = self.event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_queue)

    def _handle_event(self, event: dict):
        event_type = event["type"]

        if event_type == "AGENT_THINKING":
            self.status_label.configure(text=f"⏳ {event['sender']} is typing...")

        elif event_type == "NEW_MESSAGE":
            self._append_chat_message(
                sender=event["sender"],
                role=event["sender_role"],
                content=event["content"],
            )

        elif event_type == "MODERATOR_THINKING":
            self.status_label.configure(text="⏳ Moderator is evaluating round consensus...")

        elif event_type == "PROMPT_GATE":
            self.status_label.configure(text="🟢 Prompt Gate: User input required.")
            summary_msg = (
                f"--- ROUND SUMMARY ---\n"
                f"Consensus: {'YES' if event['consensus_reached'] else 'NO'}\n"
                f"State: {event['round_summary']}\n"
                f"Suggested: {event['suggested_message']}"
            )
            self._append_chat_message("Moderator", "assistant", summary_msg, is_summary=True)

            self.continue_btn.configure(state="normal", fg_color="#1F6AA5")
            self.end_btn.configure(state="normal")
            self.start_btn.configure(state="disabled")

        elif event_type == "SESSION_ENDED":
            self.status_label.configure(text="🔴 Session concluded.")
            self._append_chat_message("System", "system", f"Session Closed. Final Summary: {event['summary']}")
            self._reset_controls()
            self._refresh_past_groups()

    def _append_chat_message(self, sender: str, role: str, content: str, is_summary: bool = False):
        card_color = "#2B2B2B"
        border_color = None
        border_width = 0

        if role == "user":
            card_color = "#1E3A8A"
        elif is_summary:
            card_color = "#2D3748"
            border_color = "#ED8936"
            border_width = 1

        card = ctk.CTkFrame(
            self.chat_display, fg_color=card_color, border_color=border_color, border_width=border_width
        )
        card.pack(fill="x", pady=6, padx=8)

        header = ctk.CTkLabel(card, text=sender, font=ctk.CTkFont(size=12, weight="bold"))
        header.pack(anchor="w", padx=10, pady=(8, 2))

        msg_body = ctk.CTkTextbox(card, height=10, wrap="word", fg_color="transparent")
        msg_body.pack(fill="x", padx=10, pady=(0, 8))
        msg_body.insert("1.0", content)
        
        lines = int(len(content) / 60) + content.count('\n') + 1
        msg_body.configure(height=max(40, lines * 18), state="disabled")

        self.chat_display._parent_canvas.yview_moveto(1.0)

    def start_session(self):
        api_key = self.api_key_entry.get().strip()
        model_id = self.model_entry.get().strip()
        title = self.session_title_entry.get().strip() or "Untitled Session"
        initial_prompt = self.user_input_entry.get().strip()

        if not api_key:
            self.status_label.configure(text="⚠️ Please enter a valid Groq API Key.")
            return

        if not model_id:
            self.status_label.configure(text="⚠️ Please specify a model ID.")
            return

        if not initial_prompt:
            self.status_label.configure(text="⚠️ Please enter an initial brainstorming prompt.")
            return

        selected_personas = [
            p_id for p_id, (_, var) in self.persona_checkboxes.items() if var.get()
        ]

        if not selected_personas:
            self.status_label.configure(text="⚠️ Select at least one persona agent.")
            return

        for widget in self.chat_display.winfo_children():
            widget.destroy()

        self.current_group_id = db.create_chat_group(title, model_id, selected_personas)
        db.save_message(self.current_group_id, "User (Executive)", "user", initial_prompt)

        self._append_chat_message("User (Executive)", "user", initial_prompt)
        self.user_input_entry.delete(0, "end")

        self.start_btn.configure(state="disabled")
        self.status_label.configure(text="🚀 Initializing session thread...")

        self.runner = SymposiumSessionRunner(
            api_key=api_key,
            model_id=model_id,
            group_id=self.current_group_id,
            ui_callback=self._thread_callback,
        )
        self.runner.start_session()

    def on_continue(self):
        user_msg = self.user_input_entry.get().strip()
        
        self.continue_btn.configure(state="disabled", fg_color="gray")
        self.end_btn.configure(state="disabled")

        if user_msg:
            self._append_chat_message("User (Executive)", "user", user_msg)
            self.user_input_entry.delete(0, "end")
            self.runner.submit_user_action("continue_with_msg", user_msg)
        else:
            self.runner.submit_user_action("continue")

    def on_end_session(self):
        if self.runner:
            self.runner.submit_user_action("end")
        self._reset_controls()
        self._refresh_past_groups()

    def _reset_controls(self):
        self.start_btn.configure(state="normal")
        self.continue_btn.configure(state="disabled", fg_color="gray")
        self.end_btn.configure(state="disabled")


if __name__ == "__main__":
    app = SymposiumApp()
    app.mainloop()