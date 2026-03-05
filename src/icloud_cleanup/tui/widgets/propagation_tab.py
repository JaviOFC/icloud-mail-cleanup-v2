"""Propagation tab widget listing accumulated suggestions with bulk-approve."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Button, DataTable, Static

from icloud_cleanup.propagation import PropagationSuggestion


class PropagationTabWidget(VerticalScroll):
    """Displays accumulated propagation suggestions with selection and bulk-approve."""

    @dataclass
    class Applied(Message):
        """Posted when user approves selected suggestions."""

        suggestion_indices: list[int]

    DEFAULT_CSS = """
    PropagationTabWidget {
        height: 1fr;
        padding: 1;
    }
    #prop-empty { text-align: center; margin: 2; }
    #prop-table { height: 1fr; }
    #prop-actions { height: auto; dock: bottom; padding: 1; }
    #prop-actions Button { margin: 0 1; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.suggestions: list[PropagationSuggestion] = []
        self._selected: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Static(
            "No propagation suggestions yet. Approve clusters to generate suggestions.",
            id="prop-empty",
        )
        yield DataTable(id="prop-table", cursor_type="row", zebra_stripes=True)
        with Static(id="prop-actions"):
            yield Button(
                "Approve All Selected",
                id="btn-prop-approve",
                variant="success",
            )

    def on_mount(self) -> None:
        table = self.query_one("#prop-table", DataTable)
        table.add_columns("Sel", "Source", "Action", "Targets", "Emails", "Reason")
        table.display = False
        self.query_one("#prop-actions").display = False

    def add_suggestions(self, new: list[PropagationSuggestion]) -> None:
        """Append new suggestions and re-render the table."""
        start_idx = len(self.suggestions)
        self.suggestions.extend(new)
        self._render()

    def _render(self) -> None:
        empty = self.query_one("#prop-empty", Static)
        table = self.query_one("#prop-table", DataTable)
        actions = self.query_one("#prop-actions")

        if not self.suggestions:
            empty.display = True
            table.display = False
            actions.display = False
            return

        empty.display = False
        table.display = True
        actions.display = True

        table.clear()
        for i, s in enumerate(self.suggestions):
            sel = "\u2713" if i in self._selected else " "
            targets_str = ", ".join(s.target_senders[:3])
            if len(s.target_senders) > 3:
                targets_str += f" +{len(s.target_senders) - 3}"
            table.add_row(
                sel,
                s.source_sender,
                s.suggested_action,
                targets_str,
                str(len(s.target_message_ids)),
                s.reason,
                key=str(i),
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Toggle selection when Space is pressed on a row."""
        pass

    def key_space(self) -> None:
        """Toggle selection on the currently highlighted suggestion."""
        table = self.query_one("#prop-table", DataTable)
        row = table.cursor_row
        if row is None or row >= len(self.suggestions):
            return

        if row in self._selected:
            self._selected.discard(row)
            table.update_cell_at((row, 0), " ")
        else:
            self._selected.add(row)
            table.update_cell_at((row, 0), "\u2713")

    def get_selected_suggestions(self) -> list[PropagationSuggestion]:
        """Return currently selected suggestions."""
        return [self.suggestions[i] for i in sorted(self._selected) if i < len(self.suggestions)]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-prop-approve":
            if not self._selected:
                # Select all if none selected
                self._selected = set(range(len(self.suggestions)))
            self.post_message(self.Applied(suggestion_indices=sorted(self._selected)))

    def clear(self) -> None:
        self.suggestions.clear()
        self._selected.clear()
        self._render()
