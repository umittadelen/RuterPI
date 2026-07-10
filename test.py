import os
import json
import requests
import threading
from datetime import datetime, timezone

# --- 1. KIVY CONFIGURATION (Must be at the very top) ---
from kivy.config import Config

# Graphics: Fullscreen and hide mouse cursor
Config.set('graphics', 'fullscreen', '1')
Config.set('graphics', 'show_cursor', '0')
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '480')

# Input: FIX FOR DOUBLE-TYPING
# We disable 'mouse' entirely so touch isn't counted twice.
Config.set('input', 'mouse', 'none')
Config.set('input', 'hidinput', 'hidinput')

# Keyboard: Enable On-Screen Keyboard
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

# --- 2. CONFIG & HELPERS ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {"stop_id": "NSR:StopPlace:58309", "stop_name": "Grefsen stadion", "max_per_quay": 6}
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

# --- 3. UI COMPONENTS ---

class DepartureRow(BoxLayout):
    """A single line of transport data"""
    def __init__(self, line, dest, time_str, aimed_str, is_delayed, mins, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(50), padding=[dp(10), 0], **kwargs)
        
        # Highlight if arriving in 1 minute or less
        if mins <= 1:
            with self.canvas.before:
                Color(0.15, 0.15, 0.15, 1)
                self.bg_rect = Rectangle(pos=self.pos, size=self.size)
            self.bind(pos=self._update_bg, size=self._update_bg)

        # Bottom separator line
        with self.canvas.after:
            Color(0.2, 0.2, 0.2, 1)
            self.border = Line(points=[self.x, self.y, self.right, self.y], width=1)
        self.bind(pos=self._update_border, size=self._update_border)

        # 1. Line Number Pill (Fixed width 50dp)
        pill_box = BoxLayout(size_hint_x=None, width=dp(50), padding=[0, dp(8)])
        color = LINE_COLORS.get(line, (0.3, 0.3, 0.3, 1))
        with pill_box.canvas.before:
            Color(*color)
            self.pill_rect = RoundedRectangle(pos=pill_box.pos, size=(dp(45), dp(32)), radius=[dp(4)])
        pill_box.bind(pos=self._update_pill)
        pill_box.add_widget(Label(text=line, bold=True, font_size='16sp'))
        self.add_widget(pill_box)

        # 2. Destination Display (The part we fixed)
        # We set text_size so it knows where to clip, and valign/halign for alignment
        self.dest_label = Label(
            text=dest.upper(), 
            font_size='17sp', 
            halign='left', 
            valign='middle',
            shorten=True,           # Adds "..." if too long
            shorten_from='right',
            padding=[dp(10), 0]
        )
        # This binding is the magic: it tells the text box to always match the label size
        self.dest_label.bind(size=self._update_text_size)
        self.add_widget(self.dest_label)

        # 3. Time Column (Fixed width 90dp)
        time_col = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(90), padding=[0, dp(5)])
        time_col.add_widget(Label(text=time_str, font_size='20sp', bold=True, halign='right'))
        if is_delayed:
            time_col.add_widget(Label(text=aimed_str, font_size='12sp', color=(1, 1, 1, 0.5), strikethrough=True, halign='right'))
        self.add_widget(time_col)

    def _update_text_size(self, instance, value):
        # Update the internal text bounding box to match the label's actual width/height
        instance.text_size = value

    def _update_bg(self, instance, value): self.bg_rect.pos = self.pos; self.bg_rect.size = self.size
    def _update_border(self, instance, value): self.border.points = [self.x, self.y, self.right, self.y]
    def _update_pill(self, instance, value): self.pill_rect.pos = (instance.x, instance.y + dp(8))

class PlatformWidget(BoxLayout):
    """A container for a specific Quay/Platform"""
    def __init__(self, quay_id, calls, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        with self.canvas.before:
            Color(1, 1, 1, 1) # White border
            self.border = Line(rectangle=(self.x, self.y, self.width, self.height), width=1)
        self.bind(pos=self._update_border, size=self._update_border)

        # Platform Header
        header = Label(text=f"PLATFORM {quay_id}", size_hint_y=None, height=dp(30), bold=True, font_size='13sp')
        with header.canvas.before:
            Color(1, 1, 1, 0.1)
            self.h_bg = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=self._update_h_bg, size=self._update_h_bg)
        self.add_widget(header)

        # Calls
        now = datetime.now(timezone.utc)
        for c in calls[:store.cfg['max_per_quay']]:
            expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
            aimed = datetime.fromisoformat(c["aimedDepartureTime"].replace("Z", "+00:00"))
            mins = int((expected - now).total_seconds() / 60)
            t_str = "NÅ" if mins <= 0 else f"{mins} MIN" if mins < 20 else expected.strftime("%H:%M")
            delayed = abs((expected - aimed).total_seconds()) > 60
            
            self.add_widget(DepartureRow(c["serviceJourney"]["line"]["publicCode"], 
                                         c["destinationDisplay"]["frontText"], 
                                         t_str, aimed.strftime("%H:%M"), delayed, mins))
        self.add_widget(BoxLayout()) # Spacer

    def _update_border(self, instance, value): self.border.rectangle = (self.x, self.y, self.width, self.height)
    def _update_h_bg(self, instance, value): self.h_bg.pos = instance.pos; self.h_bg.size = instance.size

# --- 4. SCREENS ---

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical')
        
        # Header Bar
        header = BoxLayout(size_hint_y=None, height=dp(65), padding=[dp(15), dp(5)], spacing=dp(10))
        with header.canvas.after:
            Color(1, 1, 1, 1)
            self.line = Line(points=[0, 0, Window.width, 0], width=2)
        header.bind(size=self._update_line)

        self.stop_name = Label(text="LOADING...", font_size='22sp', bold=True, halign='left', size_hint_x=0.4)
        self.clock = Label(text="00:00", font_size='32sp', bold=True, size_hint_x=0.2)
        
        actions = BoxLayout(size_hint_x=0.4, spacing=dp(10))
        self.temp = Label(text="--°C", color=(0.7,0.7,0.7,1), size_hint_x=0.3)
        self.btn_cfg = Button(text="CONFIG", bold=True, background_color=(0.2, 0.2, 0.2, 1))
        self.btn_exit = Button(text="X", bold=True, size_hint_x=None, width=dp(50), background_color=(0.6, 0.1, 0.1, 1))
        
        actions.add_widget(self.temp)
        actions.add_widget(self.btn_cfg)
        actions.add_widget(self.btn_exit)
        
        header.add_widget(self.stop_name)
        header.add_widget(self.clock)
        header.add_widget(actions)
        
        # Board Area
        self.board_container = BoxLayout(orientation='vertical', spacing=dp(2))
        
        layout.add_widget(header)
        layout.add_widget(self.board_container)
        self.add_widget(layout)

    def _update_line(self, instance, value): self.line.points = [0, instance.y, Window.width, instance.y]

    def on_enter(self):
        Clock.schedule_interval(self.tick, 1)
        self.fetch_data()
        Clock.schedule_interval(lambda dt: self.fetch_data(), 15)

    def tick(self, dt):
        self.clock.text = datetime.now().strftime("%H:%M")
        self.temp.text = get_cpu_temp()

    def fetch_data(self):
        threading.Thread(target=self._query, daemon=True).start()

    def _query(self):
        q = f'{{ stopPlace(id: "{store.cfg["stop_id"]}") {{ estimatedCalls(numberOfDepartures: 40) {{ aimedDepartureTime expectedDepartureTime quay {{ id }} destinationDisplay {{ frontText }} serviceJourney {{ line {{ publicCode }} }} }} }} }}'
        try:
            r = requests.post("https://api.entur.io/journey-planner/v3/graphql", 
                              headers={"ET-Client-Name": "raspi-kivy"}, json={"query": q}, timeout=5)
            data = r.json()["data"]["stopPlace"]["estimatedCalls"]
            Clock.schedule_once(lambda dt: self.update_ui(data))
        except: pass

    def update_ui(self, calls):
        self.stop_name.text = store.cfg['stop_name'].upper()
        self.board_container.clear_widgets()
        
        grouped = {}
        now = datetime.now(timezone.utc)
        for c in calls:
            expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
            if 0 <= (expected - now).total_seconds() <= 3600:
                q_id = c.get("quay", {}).get("id", "??").split(":")[-1]
                grouped.setdefault(q_id, []).append(c)

        keys = sorted(grouped.keys())
        # Logic to prevent squeezing: Use horizontal rows of 2
        for i in range(0, len(keys), 2):
            chunk = keys[i:i+2]
            if len(chunk) == 2:
                row = BoxLayout(orientation='horizontal', size_hint_y=1)
                row.add_widget(PlatformWidget(chunk[0], grouped[chunk[0]], size_hint_x=0.5))
                row.add_widget(PlatformWidget(chunk[1], grouped[chunk[1]], size_hint_x=0.5))
                self.board_container.add_widget(row)
            else:
                # Odd number: last one spans full width
                self.board_container.add_widget(PlatformWidget(chunk[0], grouped[chunk[0]], size_hint_x=1.0))

class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(30), spacing=dp(15))
        layout.add_widget(Label(text="SEARCH STOP", font_size='24sp', bold=True, size_hint_y=None, height=dp(40)))
        
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
        
        self.btn_back = Button(text="CANCEL", size_hint_y=None, height=dp(60))
        layout.add_widget(self.btn_back)
        self.add_widget(layout)

    def on_search(self, instance, value):
        if len(value) > 2: threading.Thread(target=self._do_search, args=(value,), daemon=True).start()

    def _do_search(self, query):
        try:
            r = requests.get(f"https://api.entur.io/geocoder/v1/autocomplete?text={query}&layers=venue&size=6").json()
            Clock.schedule_once(lambda dt: self._show(r.get('features', [])))
        except: pass

    def _show(self, features):
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

# --- 5. APP START ---

class DepartureApp(App):
    def build(self):
        sm = ScreenManager(transition=NoTransition())
        self.main = MainScreen(name='main')
        self.sett = SettingsScreen(name='settings')
        
        # Bindings
        self.main.btn_cfg.bind(on_release=lambda x: setattr(sm, 'current', 'settings'))
        self.main.btn_exit.bind(on_release=lambda x: os._exit(0))
        self.sett.btn_back.bind(on_release=lambda x: setattr(sm, 'current', 'main'))
        
        sm.add_widget(self.main)
        sm.add_widget(self.sett)
        return sm

if __name__ == "__main__":
    DepartureApp().run()