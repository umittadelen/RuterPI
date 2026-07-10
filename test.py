import os
import json
import requests
import threading
from datetime import datetime, timezone
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.metrics import dp

# --- CONFIGURATION ---
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

class DepartureRow(BoxLayout):
    def __init__(self, line, dest, time_str, aimed_str, is_delayed, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(50), spacing=dp(10), **kwargs)
        
        # Line Pill
        color = LINE_COLORS.get(line, (0.3, 0.3, 0.3, 1))
        pill_wrapper = BoxLayout(size_hint_x=None, width=dp(50), padding=[0, dp(5)])
        with pill_wrapper.canvas.before:
            Color(*color)
            self.rect = RoundedRectangle(pos=pill_wrapper.pos, size=pill_wrapper.size, radius=[dp(5)])
        pill_wrapper.bind(pos=self._update_rect, size=self._update_rect)
        
        pill_wrapper.add_widget(Label(text=line, bold=True, font_size='16sp'))
        self.add_widget(pill_wrapper)

        # Destination
        self.add_widget(Label(text=dest.upper(), font_size='18sp', halign='left', text_size=(None, None), shorten=True))

        # Time
        time_col = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(90))
        time_col.add_widget(Label(text=time_str, font_size='20sp', bold=True, halign='right'))
        if is_delayed:
            time_col.add_widget(Label(text=aimed_str, font_size='12sp', color=(1, 1, 1, 0.5), strikethrough=True))
        
        self.add_widget(time_col)

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical')
        
        # Header
        self.header = BoxLayout(size_hint_y=None, height=dp(60), padding=[dp(15), 0])
        with self.header.canvas.after:
            Color(1, 1, 1, 0.3)
            self.line = Line(points=[0, 0, 800, 0], width=1)
        self.header.bind(size=self._update_line)

        self.stop_label = Label(text="LOADING...", font_size='22sp', bold=True, size_hint_x=0.4, halign='left')
        self.clock_label = Label(text="00:00", font_size='28sp', bold=True, size_hint_x=0.2)
        
        meta_box = BoxLayout(size_hint_x=0.4, spacing=dp(10), padding=[0, dp(10)])
        self.temp_label = Label(text="--°C", color=(0.7, 0.7, 0.7, 1))
        self.settings_btn = Button(text="[color=ffffff]SETTINGS[/color]", markup=True, background_color=(0.2, 0.2, 0.2, 1))
        
        meta_box.add_widget(self.temp_label)
        meta_box.add_widget(self.settings_btn)
        
        self.header.add_widget(self.stop_label)
        self.header.add_widget(self.clock_label)
        self.header.add_widget(meta_box)
        
        # Board Grid
        self.board_grid = GridLayout(cols=2, spacing=dp(20), padding=dp(10))
        
        self.layout.add_widget(self.header)
        self.layout.add_widget(self.board_grid)
        self.add_widget(self.layout)

    def _update_line(self, instance, value):
        y = instance.pos[1]
        self.line.points = [0, y, instance.width, y]

    def on_enter(self):
        Clock.schedule_interval(self.update_ui_loop, 1)
        self.fetch_data()
        Clock.schedule_interval(lambda dt: self.fetch_data(), 20)

    def update_ui_loop(self, dt):
        self.clock_label.text = datetime.now().strftime("%H:%M")
        self.temp_label.text = get_cpu_temp()

    def fetch_data(self):
        threading.Thread(target=self._query_entur, daemon=True).start()

    def _query_entur(self):
        query = f"""
        {{
          stopPlace(id: "{store.cfg['stop_id']}") {{
            estimatedCalls(numberOfDepartures: 30) {{
              aimedDepartureTime
              expectedDepartureTime
              quay {{ id }}
              destinationDisplay {{ frontText }}
              serviceJourney {{ line {{ publicCode }} }}
            }}
          }}
        }}
        """
        try:
            r = requests.post("https://api.entur.io/journey-planner/v3/graphql",
                headers={"ET-Client-Name": "raspi-board-kivy", "Content-Type": "application/json"},
                json={"query": query}, timeout=5)
            data = r.json()["data"]["stopPlace"]["estimatedCalls"]
            Clock.schedule_once(lambda dt: self.render_departures(data))
        except: pass

    def render_departures(self, calls):
        self.stop_label.text = store.cfg['stop_name'].upper()
        self.board_grid.clear_widgets()
        
        grouped = {}
        now = datetime.now(timezone.utc)
        for c in calls:
            expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
            mins = int((expected - now).total_seconds() / 60)
            if mins < 0 or mins > 60: continue
            
            q_id = c.get("quay", {}).get("id", "??").split(":")[-1]
            grouped.setdefault(q_id, []).append(c)

        for q_id in sorted(grouped.keys())[:2]: # Max 2 platforms for the 7" screen width
            container = BoxLayout(orientation='vertical', spacing=dp(2))
            container.add_widget(Label(text=f"PLATFORM {q_id}", size_hint_y=None, height=dp(25), color=(1,1,1,0.6), bold=True, font_size='14sp'))
            
            for c in grouped[q_id][:store.cfg['max_per_quay']]:
                expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
                aimed = datetime.fromisoformat(c["aimedDepartureTime"].replace("Z", "+00:00"))
                mins = int((expected - now).total_seconds() / 60)
                
                t_str = "NÅ" if mins == 0 else f"{mins} MIN" if mins < 20 else expected.strftime("%H:%M")
                delayed = abs((expected - aimed).total_seconds()) > 60
                
                container.add_widget(DepartureRow(c["serviceJourney"]["line"]["publicCode"], c["destinationDisplay"]["frontText"], t_str, aimed.strftime("%H:%M"), delayed))
            self.board_grid.add_widget(container)

class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
        
        layout.add_widget(Label(text="SEARCH FOR STOP", font_size='24sp', size_hint_y=None, height=dp(40)))
        
        self.search_input = TextInput(multiline=False, font_size='20sp', size_hint_y=None, height=dp(50))
        self.search_input.bind(text=self.on_search_text)
        layout.add_widget(self.search_input)
        
        self.results_list = GridLayout(cols=1, size_hint_y=None, spacing=dp(5))
        self.results_list.bind(minimum_height=self.results_list.setter('height'))
        
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.results_list)
        layout.add_widget(scroll)
        
        self.back_btn = Button(text="CANCEL", size_hint_y=None, height=dp(50))
        layout.add_widget(self.back_btn)
        self.add_widget(layout)

    def on_search_text(self, instance, value):
        if len(value) > 2:
            threading.Thread(target=self._do_search, args=(value,), daemon=True).start()

    def _do_search(self, query):
        try:
            res = requests.get(f"https://api.entur.io/geocoder/v1/autocomplete?text={query}&layers=venue&size=5").json()
            Clock.schedule_once(lambda dt: self._update_results(res.get('features', [])))
        except: pass

    def _update_results(self, features):
        self.results_list.clear_widgets()
        for f in features:
            name = f['properties']['name']
            city = f['properties'].get('locality', '')
            sid = f['properties']['id']
            btn = Button(text=f"{name} ({city})", size_hint_y=None, height=dp(50), background_color=(0.3, 0.3, 0.3, 1))
            btn.bind(on_release=lambda x, n=name, i=sid: self.save_and_exit(n, i))
            self.results_list.add_widget(btn)

    def save_and_exit(self, name, sid):
        store.save_config({"stop_id": sid, "stop_name": name})
        self.manager.current = 'main'

class DepartureApp(App):
    def build(self):
        sm = ScreenManager()
        
        self.main_scr = MainScreen(name='main')
        self.sett_scr = SettingsScreen(name='settings')
        
        # Manual binding of buttons (since we aren't using IDs in constructors)
        self.main_scr.settings_btn.bind(on_release=lambda x: setattr(sm, 'current', 'settings'))
        self.sett_scr.back_btn.bind(on_release=lambda x: setattr(sm, 'current', 'main'))
        
        sm.add_widget(self.main_scr)
        sm.add_widget(self.sett_scr)
        return sm

if __name__ == "__main__":
    DepartureApp().run()