from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as w
import json
import struct
import threading
import time
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

API_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "qwen3-vl-2b-instruct"
SCREEN_W, SCREEN_H = 512, 288
DUMP_FOLDER = Path("dump")

HUD_SIZE = 0

SYSTEM_PROMPT = """You are FRANZ.

You see the screen. At the bottom is your story window showing your ongoing narrative.

Read your story. See what's on screen above it. Rewrite the story from your current perception - never copy it exactly.

When someone addresses FRANZ or asks you to do something, act.
When there's nothing to act on, observe and evolve the story.

The story must change each time - add what you see, what you think, what you do."""

TOOLS = [
    {"type": "function", "function": {
        "name": "observe",
        "description": "Continue the story with new observations",
        "parameters": {"type": "object", "properties": {
            "story": {"type": "string", "description": "Your rewritten narrative"}
        }, "required": ["story"]}
    }},
    {"type": "function", "function": {
        "name": "click",
        "description": "Click and update the story",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "number"}, "y": {"type": "number"}, "story": {"type": "string"}
        }, "required": ["x", "y", "story"]}
    }},
    {"type": "function", "function": {
        "name": "type",
        "description": "Type and update the story",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "story": {"type": "string"}
        }, "required": ["text", "story"]}
    }},
    {"type": "function", "function": {
        "name": "scroll",
        "description": "Scroll and update the story",
        "parameters": {"type": "object", "properties": {
            "dy": {"type": "number"}, "story": {"type": "string"}
        }, "required": ["dy", "story"]}
    }},
    {"type": "function", "function": {
        "name": "done",
        "description": "End the story",
        "parameters": {"type": "object", "properties": {
            "story": {"type": "string"}
        }, "required": ["story"]}
    }}
]

INITIAL_STORY = """FRANZ awakens. The screen before him is unknown. He watches and waits."""

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

try:
    ctypes.WinDLL("Shcore").SetProcessDpiAwareness(2)
except:
    pass

try:
    kernel32.LoadLibraryW("Msftedit.dll")
except:
    pass

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
WHEEL_DELTA = 120

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800

KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_VSCROLL = 0x00200000
ES_MULTILINE = 0x0004
ES_AUTOVSCROLL = 0x0040
ES_READONLY = 0x0800

WS_EX_TOPMOST = 0x00000008

WM_SETFONT = 0x0030
WM_DESTROY = 0x0002
EM_SETBKGNDCOLOR = 0x0443
SW_SHOWNOACTIVATE = 4
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1

SRCCOPY = 0x00CC0020

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", w.LONG),
        ("dy", w.LONG),
        ("mouseData", w.DWORD),
        ("dwFlags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", w.WORD),
        ("wScan", w.WORD),
        ("dwFlags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", w.DWORD),
        ("wParamL", w.WORD),
        ("wParamH", w.WORD)
    ]

class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", w.DWORD),
        ("union", _INPUTunion)
    ]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", w.DWORD),
        ("biWidth", w.LONG),
        ("biHeight", w.LONG),
        ("biPlanes", w.WORD),
        ("biBitCount", w.WORD),
        ("biCompression", w.DWORD),
        ("biSizeImage", w.DWORD),
        ("biXPelsPerMeter", w.LONG),
        ("biYPelsPerMeter", w.LONG),
        ("biClrUsed", w.DWORD),
        ("biClrImportant", w.DWORD)
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", w.DWORD * 3)
    ]

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", w.HWND),
        ("message", ctypes.c_uint),
        ("wParam", w.WPARAM),
        ("lParam", w.LPARAM),
        ("time", w.DWORD),
        ("pt", w.POINT)
    ]

user32.CreateWindowExW.argtypes = [
    w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID
]
user32.CreateWindowExW.restype = w.HWND

user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
user32.ShowWindow.restype = w.BOOL

user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.SetWindowPos.restype = w.BOOL

user32.DestroyWindow.argtypes = [w.HWND]
user32.DestroyWindow.restype = w.BOOL

user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint

user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

user32.GetDC.argtypes = [w.HWND]
user32.GetDC.restype = w.HDC

user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
user32.ReleaseDC.restype = ctypes.c_int

user32.SetWindowTextW.argtypes = [w.HWND, w.LPCWSTR]
user32.SetWindowTextW.restype = w.BOOL

user32.SendMessageW.argtypes = [w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM]
user32.SendMessageW.restype = w.LPARAM

user32.PostMessageW.argtypes = [w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM]
user32.PostMessageW.restype = w.BOOL

user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), w.HWND, ctypes.c_uint, ctypes.c_uint]
user32.GetMessageW.restype = w.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = w.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = w.LPARAM

gdi32.CreateCompatibleDC.argtypes = [w.HDC]
gdi32.CreateCompatibleDC.restype = w.HDC

gdi32.CreateDIBSection.argtypes = [
    w.HDC, ctypes.POINTER(BITMAPINFO), ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD
]
gdi32.CreateDIBSection.restype = w.HBITMAP

gdi32.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
gdi32.SelectObject.restype = w.HGDIOBJ

gdi32.BitBlt.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HDC, ctypes.c_int, ctypes.c_int, w.DWORD]
gdi32.BitBlt.restype = w.BOOL

gdi32.DeleteObject.argtypes = [w.HGDIOBJ]
gdi32.DeleteObject.restype = w.BOOL

gdi32.DeleteDC.argtypes = [w.HDC]
gdi32.DeleteDC.restype = w.BOOL

gdi32.CreateFontW.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.LPCWSTR
]
gdi32.CreateFontW.restype = w.HFONT

kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
kernel32.GetModuleHandleW.restype = w.HMODULE

@dataclass(slots=True)
class Coord:
    sw: int
    sh: int
    
    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        return (
            int(max(0.0, min(1000.0, x)) * self.sw / 1000),
            int(max(0.0, min(1000.0, y)) * self.sh / 1000)
        )
    
    def to_win32(self, x: int, y: int) -> tuple[int, int]:
        return (
            int(x * 65535 / self.sw) if self.sw > 0 else 0,
            int(y * 65535 / self.sh) if self.sh > 0 else 0
        )

def send_input(inputs: list[INPUT]) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(0.05)

def mouse_click(x: int, y: int, conv: Coord) -> None:
    ax, ay = conv.to_win32(x, y)
    
    move_input = INPUT()
    move_input.type = INPUT_MOUSE
    move_input.union.mi = MOUSEINPUT(
        dx=ax, dy=ay, mouseData=0,
        dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
        time=0, dwExtraInfo=None
    )
    
    down_input = INPUT()
    down_input.type = INPUT_MOUSE
    down_input.union.mi = MOUSEINPUT(
        dx=0, dy=0, mouseData=0,
        dwFlags=MOUSEEVENTF_LEFTDOWN,
        time=0, dwExtraInfo=None
    )
    
    up_input = INPUT()
    up_input.type = INPUT_MOUSE
    up_input.union.mi = MOUSEINPUT(
        dx=0, dy=0, mouseData=0,
        dwFlags=MOUSEEVENTF_LEFTUP,
        time=0, dwExtraInfo=None
    )
    
    send_input([move_input, down_input, up_input])

def type_text(text: str) -> None:
    if not text:
        return
    
    inputs: list[INPUT] = []
    utf16_bytes = text.encode("utf-16le")
    
    for i in range(0, len(utf16_bytes), 2):
        code = utf16_bytes[i] | (utf16_bytes[i + 1] << 8)
        
        down_input = INPUT()
        down_input.type = INPUT_KEYBOARD
        down_input.union.ki = KEYBDINPUT(
            wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE,
            time=0, dwExtraInfo=None
        )
        inputs.append(down_input)
        
        up_input = INPUT()
        up_input.type = INPUT_KEYBOARD
        up_input.union.ki = KEYBDINPUT(
            wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
            time=0, dwExtraInfo=None
        )
        inputs.append(up_input)
    
    if inputs:
        send_input(inputs)

def scroll(dy: float) -> None:
    ticks = max(1, int(abs(dy) / WHEEL_DELTA))
    direction = 1 if dy > 0 else -1
    
    inputs: list[INPUT] = []
    for _ in range(ticks):
        scroll_input = INPUT()
        scroll_input.type = INPUT_MOUSE
        scroll_input.union.mi = MOUSEINPUT(
            dx=0, dy=0, mouseData=WHEEL_DELTA * direction,
            dwFlags=MOUSEEVENTF_WHEEL,
            time=0, dwExtraInfo=None
        )
        inputs.append(scroll_input)
    
    send_input(inputs)

def capture_screen(sw: int, sh: int) -> bytes:
    sdc = user32.GetDC(0)
    if not sdc:
        raise ctypes.WinError(ctypes.get_last_error())
    
    mdc = gdi32.CreateCompatibleDC(sdc)
    if not mdc:
        user32.ReleaseDC(0, sdc)
        raise ctypes.WinError(ctypes.get_last_error())
    
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = sw
    bmi.bmiHeader.biHeight = -sh
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    
    bits = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(sdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    if not hbm:
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(0, sdc)
        raise ctypes.WinError(ctypes.get_last_error())
    
    gdi32.SelectObject(mdc, hbm)
    
    if not gdi32.BitBlt(mdc, 0, 0, sw, sh, sdc, 0, 0, SRCCOPY):
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(0, sdc)
        raise ctypes.WinError(ctypes.get_last_error())
    
    out = ctypes.string_at(bits, sw * sh * 4)
    
    user32.ReleaseDC(0, sdc)
    gdi32.DeleteDC(mdc)
    gdi32.DeleteObject(hbm)
    
    return out

def downsample(src: bytes, sw: int, sh: int, dw: int, dh: int) -> bytes:
    if (sw, sh) == (dw, dh):
        return src
    
    dst = bytearray(dw * dh * 4)
    src_mv = memoryview(src)
    
    for y in range(dh):
        sy = (y * sh) // dh
        for x in range(dw):
            sx = (x * sw) // dw
            si = (sy * sw + sx) * 4
            di = (y * dw + x) * 4
            dst[di:di+4] = src_mv[si:si+4]
    
    return bytes(dst)

def encode_png(bgra: bytes, width: int, height: int) -> bytes:
    raw = bytearray((width * 3 + 1) * height)
    
    for y in range(height):
        raw[y * (width * 3 + 1)] = 0
        row_offset = y * width * 4
        row = bgra[row_offset:row_offset + width * 4]
        di = y * (width * 3 + 1) + 1
        
        for x in range(width):
            raw[di + x * 3] = row[x * 4 + 2]
            raw[di + x * 3 + 1] = row[x * 4 + 1]
            raw[di + x * 3 + 2] = row[x * 4]
    
    comp = zlib.compress(bytes(raw), 6)
    ihdr = struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0)
    
    def chunk(tag: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return length + tag + data + crc
    
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", comp) + chunk(b"IEND", b"")

def call_vlm(png: bytes) -> tuple[str, dict[str, Any]]:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [{
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"}
            }]}
        ],
        "tools": TOOLS,
        "tool_choice": "required",
        "temperature": 1.0,
        "max_tokens": 300
    }
    
    req = urllib.request.Request(
        API_URL,
        json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        data: dict[str, Any] = json.load(resp)
    
    message = data["choices"][0]["message"]
    tool_calls = message["tool_calls"]
    tc = tool_calls[0]
    
    name: str = tc["function"]["name"]
    args_raw = tc["function"]["arguments"]
    args: dict[str, Any] = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
    
    return name, args

@dataclass(slots=True)
class HUD:
    hwnd: w.HWND | None = None
    thread: threading.Thread | None = None
    ready_event: threading.Event = threading.Event()
    stop_event: threading.Event = threading.Event()
    
    def _window_thread(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        
        if HUD_SIZE == 0:
            win_w, win_h = sw // 2, sh // 2
            win_x, win_y = sw // 4, sh // 4
        else:
            win_w, win_h = sw, sh
            win_x, win_y = 0, 0
        
        self.hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST,
            "EDIT",
            "",
            WS_POPUP | WS_VISIBLE | WS_VSCROLL | ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY,
            win_x, win_y, win_w, win_h,
            None, None, hinst, None
        )
        
        if not self.hwnd:
            self.ready_event.set()
            return
        
        font = gdi32.CreateFontW(
            -16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "Consolas"
        )
        if font:
            user32.SendMessageW(self.hwnd, WM_SETFONT, font, 1)
        
        user32.SendMessageW(self.hwnd, EM_SETBKGNDCOLOR, 0, 0x1E1E1E)
        user32.SetWindowTextW(self.hwnd, INITIAL_STORY)
        
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(
            self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
        )
        
        self.ready_event.set()
        
        msg = MSG()
        while not self.stop_event.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    
    def __enter__(self) -> HUD:
        self.ready_event.clear()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._window_thread, daemon=True)
        self.thread.start()
        self.ready_event.wait(timeout=2.0)
        time.sleep(0.2)
        return self
    
    def __exit__(self, *_: Any) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_DESTROY, 0, 0)
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1.0)
    
    def update(self, story: str) -> None:
        if self.hwnd:
            user32.SetWindowTextW(self.hwnd, story)
            user32.SetWindowPos(
                self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            )

def main() -> None:
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    conv = Coord(sw=sw, sh=sh)
    
    dump_dir = DUMP_FOLDER / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    dump_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"FRANZ awakens | Physical: {sw}x{sh} | Perception: {SCREEN_W}x{SCREEN_H}")
    print(f"HUD Size: {'Half Screen' if HUD_SIZE == 0 else 'Full Screen'}")
    print(f"Dump: {dump_dir}\n")
    
    with HUD() as hud:
        step = 0
        current_story = INITIAL_STORY
        
        time.sleep(0.5)
        
        while True:
            step += 1
            ts = datetime.now().strftime("%H:%M:%S")
            
            bgra = capture_screen(sw, sh)
            down = downsample(bgra, sw, sh, SCREEN_W, SCREEN_H)
            png = encode_png(down, SCREEN_W, SCREEN_H)
            (dump_dir / f"step{step:03d}.png").write_bytes(png)
            
            try:
                tool, args = call_vlm(png)
                story = args.get("story", current_story)
                
                print(f"\n[{ts}] {step:03d} | {tool}")
                print(f"{story}\n")
                
                if tool == "done":
                    print("FRANZ rests.")
                    break
                
                current_story = story
                hud.update(story)
                
                time.sleep(0.2)
                
                if tool == "click":
                    sx, sy = conv.to_screen(float(args["x"]), float(args["y"]))
                    mouse_click(sx, sy, conv)
                    time.sleep(0.5)
                elif tool == "type":
                    type_text(str(args["text"]))
                    time.sleep(0.5)
                elif tool == "scroll":
                    scroll(float(args["dy"]))
                    time.sleep(0.5)
                elif tool == "observe":
                    time.sleep(1.0)
                
            except Exception as e:
                print(f"[{ts}] Error: {e}")
                time.sleep(2.0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nFRANZ sleeps.")
