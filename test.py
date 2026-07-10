import os
import json
import requests
import threading
from datetime import datetime, timezone

# --- KIVY CONFIG (MUST BE AT THE VERY TOP) ---
from kivy.config import Config

# 1. Fullscreen and Cursor
Config.set('graphics', 'fullscreen', '1')
Config.set('graphics', 'show_cursor', '0')

# 2. THE FIX FOR DOUBLE TYPING
# We disable the 'mouse' provider entirely. This stops Kivy from 
# seeing one touch as both a mouse-click and a touch-event.
Config.set('input', 'mouse', 'none')
# We force Kivy to use the HID (Touchscreen) provider directly
Config.set('input', 'mtdev', 'none')
Config.set('input', 'hidinput', 'hidinput')

# 3. Keyboard settings
Config.set('kivy', 'keyboard_mode', 'systemanddock')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Line, Rectangle
from kivy.metrics import dp
from kivy.core.window import Window

# --- CONFIGURATION & DATA ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {"stop_id": "NSR:StopPlace:58309", "stop_name": "Grefsen stadion", "max_per_quay": 10}
LINE_COLORS = { "25": (0.42, 0.18, 0.63, 1), "26": (0, 0.19, 0.53, 1), "31": (0.91, 0, 0.11, 1), "60": (0, 0.48, 0.25, 1) }

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return f"{int(f.read()) / 1000:.1f}°C"
    except: return "??°C"

class DataStore:
    def __init__(self):
        self.cfg = self.load_config()
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                try: return {**DEFAULT_CONFIG, **json.load(f)}
                except: return DEFAULT_CONFIG
        return DEFAULT_CONFIG
    def save_config(self, data):
        self.cfg.update(data)
        with open(CONFIG_FILE, "w") as f: json.dump(self.cfg, f, indent=2)

store = DataStore()

# --- UI CLASSES ---

class DepartureRow(BoxLayout):
    def __init__(self, line, dest, time_str, aimed_str, is_delayed, mins, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(55), padding=[dp(10), 0], **kwargs)
        if mins <= 1:
            with self.canvas.before:
                Color(0.1, 0.1, 0.1, 1)
                self.bg_rect = Rectangle(pos=self.pos, size=self.size)
            self.bind(pos=self._update_bg, size=self._update_bg)

        with self.canvas.after:
            Color(0.2, 0.2, 0.2, 1)
            self.border = Line(points=[self.x, self.y, self.right, self.y], width=1)
        self.bind(pos=self._update_border, size=self._update_border)

        # Line Pill
        pill_container = BoxLayout(size_hint_x=None, width=dp(55), padding=[0, dp(10)])
        color = LINE_COLORS.get(line, (0.3, 0.3, 0.3, 1))
        with pill_container.canvas.before:
            Color(*color)
            self.pill_rect = RoundedRectangle(pos=pill_container.pos, size=(dp(48), dp(32)), radius=[dp(4)])
        pill_container.bind(pos=self._update_pill)
        pill_container.add_widget(Label(text=line, bold=True, font_size='16sp'))
        self.add_widget(pill_container)

        # Dest
        self.add_widget(Label(text=dest.upper(), font_size='20sp', halign='left', text_size=(None, None), padding=[dp(10), 0]))

        # Time
        time_col = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(100), padding=[0, dp(5)])
        time_col.add_widget(Label(text=time_str, font_size='22sp', bold=True, halign='right'))
        if is_delayed:
            time_col.add_widget(Label(text=aimed_str, font_size='13sp', color=(1, 1, 1, 0.5), strikethrough=True, halign='right'))
        self.add_widget(time_col)

    def _update_bg(self, instance, value): self.bg_rect.pos = self.pos; self.bg_rect.size = self.size
    def _update_border(self, instance, value): self.border.points = [self.x, self.y, self.right, self.y]
    def _update_pill(self, instance, value): self.pill_rect.pos = (instance.x, instance.y + dp(10))

class PlatformWidget(BoxLayout):
    def __init__(self, quay_id, calls, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.border = Line(rectangle=(self.x, self.y, self.width, self.height), width=1)
        self.bind(pos=self._update_border, size=self._update_border)

        header = Label(text=f"PLATFORM {quay_id}", size_hint_y=None, height=dp(35), 
                       bold=True, halign='left', padding=[dp(15), 0], font_size='14sp')
        with header.canvas.before:
            Color(1,1,1,0.1)
            self.header_bg = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=self._update_header_bg, size=self._update_header_bg)
        self.add_widget(header)

        now = datetime.now(timezone.utc)
        for c in calls[:store.cfg['max_per_quay']]:
            expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
            aimed = datetime.fromisoformat(c["aimedDepartureTime"].replace("Z", "+00:00"))
            mins = int((expected - now).total_seconds() / 60)
            t_str = "NÅ" if mins == 0 else f"{mins} MIN" if mins < 20 else expected.strftime("%H:%M")
            delayed = abs((expected - aimed).total_seconds()) > 60
            self.add_widget(DepartureRow(c["serviceJourney"]["line"]["publicCode"], c["destinationDisplay"]["frontText"], t_str, aimed.strftime("%H:%M"), delayed, mins))
        self.add_widget(BoxLayout())

    def _update_border(self, instance, value): self.border.rectangle = (self.x, self.y, self.width, self.height)
    def _update_header_bg(self, instance, value): self.header_bg.pos = instance.pos; self.header_bg.size = instance.size

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical')
        
        # Header
        header_bar = BoxLayout(size_hint_y=None, height=dp(70), padding=[dp(15), dp(5)])
        with header_bar.canvas.after:
            Color(1, 1, 1, 1)
            self.line = Line(points=[0, 0, Window.width, 0], width=2)
        header_bar.bind(size=self._update_line)

        self.stop_label = Label(text="LOADING...", font_size='22sp', bold=True, halign='left', size_hint_x=0.4)
        self.clock_label = Label(text="00:00", font_size='34sp', bold=True, size_hint_x=0.2)
        
        # Action Buttons (Config and Exit)
        actions = BoxLayout(size_hint_x=0.4, spacing=dp(10))
        self.temp_label = Label(text="--°C", size_hint_x=0.3, color=(0.7,0.7,0.7,1))
        
        self.config_btn = Button(text="CONFIG", bold=True, background_color=(0.2, 0.2, 0.2, 1))
        self.exit_btn = Button(text="X", bold=True, size_hint_x=None, width=dp(60), background_color=(0.6, 0.1, 0.1, 1))
        
        actions.add_widget(self.temp_label)
        actions.add_widget(self.config_btn)
        actions.add_widget(self.exit_btn)
        
        header_bar.add_widget(self.stop_label)
        header_bar.add_widget(self.clock_label)
        header_bar.add_widget(actions)
        
        self.board_grid = GridLayout(cols=2)
        self.layout.add_widget(header_bar)
        self.layout.add_widget(self.board_grid)
        self.add_widget(self.layout)

    def _update_line(self, instance, value): self.line.points = [0, instance.y, Window.width, instance.y]

    def on_enter(self):
        Clock.schedule_interval(self.tick, 1)
        self.fetch()
        Clock.schedule_interval(lambda dt: self.fetch(), 15)

    def tick(self, dt):
        self.clock_label.text = datetime.now().strftime("%H:%M")
        self.temp_label.text = get_cpu_temp()

    def fetch(self):
        threading.Thread(target=self._do_fetch, daemon=True).start()

    def _do_fetch(self):
        query = f'{{ stopPlace(id: "{store.cfg["stop_id"]}") {{ estimatedCalls(numberOfDepartures: 40) {{ aimedDepartureTime expectedDepartureTime quay {{ id }} destinationDisplay {{ frontText }} serviceJourney {{ line {{ publicCode }} }} }} }} }}'
        try:
            r = requests.post("https://api.entur.io/journey-planner/v3/graphql", headers={"ET-Client-Name": "raspi-kivy"}, json={"query": query}, timeout=5)
            calls = r.json()["data"]["stopPlace"]["estimatedCalls"]
            Clock.schedule_once(lambda dt: self.update_board(calls))
        except: pass

    def update_board(self, calls):
        self.stop_label.text = store.cfg['stop_name'].upper()
        self.board_grid.clear_widgets()
        grouped = {}
        now = datetime.now(timezone.utc)
        for c in calls:
            expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
            if 0 <= (expected - now).total_seconds() <= 3600:
                q_id = c.get("quay", {}).get("id", "??").split(":")[-1]
                grouped.setdefault(q_id, []).append(c)

        keys = sorted(grouped.keys())
        for i, q_id in enumerate(keys):
            is_odd_last = (i == len(keys) - 1 and len(keys) % 2 != 0)
            self.board_grid.add_widget(PlatformWidget(q_id, grouped[q_id], size_hint_x=1.0 if is_odd_last else 0.5))

class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(30), spacing=dp(15))
        layout.add_widget(Label(text="SEARCH FOR STOP", font_size='24sp', bold=True, size_hint_y=None, height=dp(40)))
        
        # Added keyboard_suggestions=False to help with ghost inputs
        self.inp = TextInput(multiline=False, font_size='28sp', size_hint_y=None, height=dp(60), 
                             background_color=(0.1,0.1,0.1,1), foreground_color=(1,1,1,1),
                             keyboard_suggestions=False)
        self.inp.bind(text=self.on_search)
        layout.add_widget(self.inp)
        
        self.results = GridLayout(cols=1, size_hint_y=None, spacing=dp(5))
        self.results.bind(minimum_height=self.results.setter('height'))
        
        scroll = ScrollView()
        scroll.add_widget(self.results)
        layout.add_widget(scroll)
        
        self.back = Button(text="CLOSE SETTINGS", size_hint_y=None, height=dp(60))
        layout.add_widget(self.back)
        self.add_widget(layout)

    def on_search(self, instance, value):
        if len(value) > 2: threading.Thread(target=self._do_search, args=(value,), daemon=True).start()

    def _do_search(self, query):
        try:
            res = requests.get(f"https://api.entur.io/geocoder/v1/autocomplete?text={query}&layers=venue&size=6").json()
            Clock.schedule_once(lambda dt: self._show_res(res.get('features', [])))
        except: pass

    def _show_res(self, features):
        self.results.clear_widgets()
        for f in features:
            name, sid = f['properties']['name'], f['properties']['id']
            city = f['properties'].get('locality', '')
            btn = Button(text=f"{name.upper()} ({city.upper()})", size_hint_y=None, height=dp(55))
            btn.bind(on_release=lambda x, n=name, s=sid: self.select(n, s))
            self.results.add_widget(btn)

    def select(self, name, sid):
        store.save_config({"stop_id": sid, "stop_name": name})
        App.get_running_app().root.current = 'main'

class DepartureApp(App):
    def build(self):
        sm = ScreenManager(transition=NoTransition())
        main = MainScreen(name='main')
        sett = SettingsScreen(name='settings')
        
        # Button bindings
        main.config_btn.bind(on_release=lambda x: setattr(sm, 'current', 'settings'))
        main.exit_btn.bind(on_release=self.exit_app)
        sett.back.bind(on_release=lambda x: setattr(sm, 'current', 'main'))
        
        sm.add_widget(main)
        sm.add_widget(sett)
        return sm

    def exit_app(self, instance):
        # Clean exit for Raspberry Pi
        os._exit(0)

if __name__ == "__main__":
    DepartureApp().run()