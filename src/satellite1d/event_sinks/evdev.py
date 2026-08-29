"""Optional Linux evdev sink for daemon button events."""

from satellite1d.contracts.events import ButtonPressed, DaemonEvent, MicMuteChanged


class EvdevButtonSink:
    def __init__(self, keymap: dict[str, str]) -> None:
        from evdev import UInput, ecodes

        self._ecodes = ecodes
        self._codes = self.validate_keymap(keymap, ecodes.ecodes)
        self._uinput = UInput(
            {ecodes.EV_KEY: list(self._codes.values())}, name="Satellite1 Buttons"
        )

    @staticmethod
    def validate_keymap(
        keymap: dict[str, str], codes: dict[str, int] | None = None
    ) -> dict[str, int]:
        if codes is None:
            from evdev import ecodes

            codes = ecodes.ecodes
        validated: dict[str, int] = {}
        for name, key in keymap.items():
            code = codes.get(key)
            if not isinstance(code, int):
                raise ValueError(
                    f"buttons.evdev.{name} is not a valid Linux key: {key}"
                )
            validated[name] = code
        return validated

    def emit(self, event: DaemonEvent) -> None:
        name: str
        if isinstance(event, ButtonPressed):
            name = event.name
        elif isinstance(event, MicMuteChanged):
            name = "mic_mute"
        else:
            return
        code = self._codes.get(name)
        if code is None:
            return
        self._uinput.write(self._ecodes.EV_KEY, code, 1)
        self._uinput.write(self._ecodes.EV_KEY, code, 0)
        self._uinput.syn()

    def close(self) -> None:
        self._uinput.close()
