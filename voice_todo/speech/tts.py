import pyttsx3
import threading


_engine = None


def _get_engine() -> pyttsx3.Engine:
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
        _engine.setProperty("rate", 160)
    return _engine


def speak(text: str, rate: int = 160, voice: str = "", blocking: bool = True):
    engine = _get_engine()
    engine.setProperty("rate", rate)

    if voice:
        voices = engine.getProperty("voices")
        for v in voices:
            if voice.lower() in v.name.lower():
                engine.setProperty("voice", v.id)
                break

    if blocking:
        engine.say(text)
        engine.runAndWait()
    else:
        def _run():
            engine.say(text)
            engine.runAndWait()
        t = threading.Thread(target=_run, daemon=True)
        t.start()


def speak_briefing(tasks_text: str, rate: int = 160):
    engine = _get_engine()
    engine.setProperty("rate", rate)
    engine.say(tasks_text)
    engine.runAndWait()


def list_voices() -> list[dict]:
    engine = _get_engine()
    voices = engine.getProperty("voices")
    return [{"id": v.id, "name": v.name, "languages": v.languages} for v in voices]