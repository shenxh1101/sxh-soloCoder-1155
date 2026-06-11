import sys

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


def _check_deps():
    if not HAS_SR:
        raise RuntimeError(
            "需要安装 speechrecognition: pip install speechrecognition"
        )
    if not HAS_PYAUDIO:
        raise RuntimeError(
            "需要安装 PyAudio 以支持麦克风输入。\n"
            "Windows 用户请下载预编译版本: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio\n"
            "或使用 conda: conda install pyaudio"
        )


def recognize_speech(language: str = "zh-CN", engine: str = "google") -> str:
    _check_deps()
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("🎤 正在监听... 请说话（按 Ctrl+C 取消）")
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=10, phrase_time_limit=15)
    except OSError as e:
        raise RuntimeError(f"无法访问麦克风: {e}")
    except sr.WaitTimeoutError:
        return ""

    print("🔍 正在识别...")
    try:
        if engine == "google":
            text = r.recognize_google(audio, language=language)
        elif engine == "sphinx":
            text = r.recognize_sphinx(audio, language=language)
        else:
            text = r.recognize_google(audio, language=language)
        return text
    except sr.UnknownValueError:
        print("⚠️ 未能识别语音内容")
        return ""
    except sr.RequestError as e:
        raise RuntimeError(f"语音识别服务请求失败: {e}")


def recognize_from_file(file_path: str, language: str = "zh-CN", engine: str = "google") -> str:
    if not HAS_SR:
        raise RuntimeError("需要安装 speechrecognition: pip install speechrecognition")
    r = sr.Recognizer()
    try:
        with sr.AudioFile(file_path) as source:
            audio = r.record(source)
    except Exception as e:
        raise RuntimeError(f"无法读取音频文件: {e}")

    print("🔍 正在识别音频文件...")
    try:
        if engine == "google":
            text = r.recognize_google(audio, language=language)
        elif engine == "sphinx":
            text = r.recognize_sphinx(audio, language=language)
        else:
            text = r.recognize_google(audio, language=language)
        return text
    except sr.UnknownValueError:
        print("⚠️ 未能识别语音内容")
        return ""
    except sr.RequestError as e:
        raise RuntimeError(f"语音识别服务请求失败: {e}")


def is_microphone_available() -> bool:
    if not HAS_PYAUDIO:
        return False
    if not HAS_SR:
        return False
    try:
        with sr.Microphone() as source:
            return True
    except OSError:
        return False