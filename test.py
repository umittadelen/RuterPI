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
        self.departures = []

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

# --- UI COMPONENTS ---

class DepartureRow(BoxLayout):
    def __init__(self, line, dest, time_str, aimed_str, is_delayed, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(60), padding=[10, 5], spacing=15, **kwargs)
        
        # Line Pill
        color = LINE_COLORS.get(line, (0.3, 0.3, 0.3, 1))
        pill_box = BoxLayout(size_hint_x=None, width=dp(55))
        with pill_box.canvas.before:
            Color(*color)
            RoundedRectangle(pos=pill_box.pos, size=(dp(50), dp(35)), radius=[5])
        
        pill_box.add_widget(Label(text=line, bold=True, font_size='18sp', halign='center'))
        self.add_widget(pill_box)

        # Destination
        self.add_widget(Label(text=dest.upper(), font_size='20sp', halign='left', text_size=(None, None), shorten=True, shorten_from='right'))

        # Time Column
        time_box = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(100))
        time_label = Label(text=time_str, font_size='22sp', bold=True, halign='right')
        time_box.add_widget(time_label)
        
        if is_delayed:
            aimed_label = Label(text=aimed_str, font_size='14sp', color=(1, 1, 1, 0.6), halign='right')
            # Strikethrough effect via canvas
            with aimed_label.canvas:
                Color(1, 1, 1, 0.5)
                Line(points=[aimed_label.center_x - 20, aimed_label.center_y, aimed_label.center_x + 20, aimed_label.center_y], width=1)
            time_box.add_widget(aimed_label)
            
        self.add_widget(time_box)

class MainScreen(Screen):
    def on_enter(self):
        self.update_data()
        Clock.schedule_interval(self.update_clock, 1)
        Clock.schedule_interval(self.update_data, 15)

    def update_clock(self, dt):
        self.ids.clock_label.text = datetime.now().strftime("%H:%M")
        self.ids.temp_label.text = get_cpu_temp()

    def update_data(self, *args):
        threading.Thread(target=self.fetch_entur_data).start()

    def fetch_entur_data(self):
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
            calls = r.json()["data"]["stopPlace"]["estimatedCalls"]
            Clock.schedule_once(lambda dt: self.render_board(calls))
        except Exception as e:
            print(f"Fetch error: {e}")

    def render_board(self, calls):
        self.ids.stop_name.text = store.cfg['stop_name'].upper()
        grid = self.ids.board_grid
        grid.clear_widgets()
        
        # Group by quay
        grouped = {}
        now = datetime.now(timezone.utc)
        for c in calls:
            expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
            mins = int((expected - now).total_seconds() / 60)
            if mins < 0 or mins > 60: continue
            
            q_id = c.get("quay", {}).get("id", "??").split(":")[-1]
            entries = grouped.setdefault(q_id, [])
            if len(entries) < store.cfg["max_per_quay"]:
                entries.append(c)

        # Draw columns
        for q_id in sorted(grouped.keys()):
            quay_col = BoxLayout(orientation='vertical', size_hint_x=0.5, padding=5)
            quay_col.add_widget(Label(text=f"PLATFORM {q_id}", size_hint_y=None, height=dp(30), bold=True, color=(1,1,1,0.8)))
            
            for c in grouped[q_id]:
                expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
                aimed = datetime.fromisoformat(c["aimedDepartureTime"].replace("Z", "+00:00"))
                mins = int((expected - now).total_seconds() / 60)
                
                time_str = "NÅ" if mins == 0 else f"{mins} MIN" if mins < 20 else expected.strftime("%H:%M")
                is_delayed = abs((expected - aimed).total_seconds()) > 60
                
                quay_col.add_widget(DepartureRow(
                    c["serviceJourney"]["line"]["publicCode"],
                    c["destinationDisplay"]["frontText"],
                    time_str,
                    aimed.strftime("%H:%M"),
                    is_delayed
                ))
            grid.add_widget(quay_col)

class SettingsScreen(Screen):
    def on_pre_enter(self):
        self.ids.search_input.text = ""
        self.ids.results_list.clear_widgets()

    def search_stop(self, text):
        if len(text) < 3: return
        def run_search():
            try:
                res = requests.get(f"https://api.entur.io/geocoder/v1/autocomplete?text={text}&layers=venue&size=5").json()
                Clock.schedule_once(lambda dt: self.display_results(res.get('features', [])))
            except: pass
        threading.Thread(target=run_search).start()

    def display_results(self, features):
        self.ids.results_list.clear_widgets()
        for f in features:
            btn = Button(text=f"{f['properties']['name']} ({f['properties'].get('locality','')})", 
                         size_hint_y=None, height=dp(60), background_color=(0.2,0.2,0.2,1))
            btn.bind(on_release=lambda x, f=f: self.select_stop(f))
            self.ids.results_list.add_widget(btn)

    def select_stop(self, f):
        store.save_config({"stop_id": f['properties']['id'], "stop_name": f['properties']['name']})
        self.manager.current = 'main'

class DepartureApp(App):
    def build(self):
        # Build UI structure in Python to avoid separate .kv file for portability
        sm = ScreenManager()
        
        # MAIN SCREEN
        main = MainScreen(name='main')
        layout = BoxLayout(orientation='vertical')
        
        # Header
        header = BoxLayout(size_hint_y=None, height=dp(70), padding=[20, 0])
        with header.canvas.after:
            Color(1, 1, 1, 1)
            Line(points=[0, dp(1210), 800, dp(1210)], width=1.5) # Resolution adjusted for Pi 7" (800x480)

        header.add_widget(Label(id='stop_name', text="---", font_size='24sp', bold=True, halign='left'))
        header.add_widget(Label(id='clock_label', text="00:00", font_size='32sp', bold=True))
        
        actions = BoxLayout(size_hint_x=None, width=dp(180), spacing=10)
        actions.add_widget(Label(id='temp_label', text="--°C", color=(0.8, 0.8, 0.8, 1)))
        
        settings_btn = Button(text="SET", size_hint=(None, None), size=(dp(50), dp(50)), pos_hint={'center_y': .5})
        settings_btn.bind(on_release=lambda x: setattr(sm, 'current', 'settings'))
        actions.add_widget(settings_btn)
        
        header.add_widget(actions)
        layout.add_widget(header)
        
        # Board
        board = GridLayout(id='board_grid', cols=2, padding=10, spacing=20)
        layout.add_widget(board)
        
        main.add_widget(layout)
        main.ids = { 'stop_name': main.ids.get('stop_name', header.children[2]), 
                     'clock_label': header.children[1],
                     'temp_label': actions.children[1],
                     'board_grid': board }

        # SETTINGS SCREEN
        sett = SettingsScreen(name='settings')
        s_layout = BoxLayout(orientation='vertical', padding=40, spacing=20)
        s_layout.add_widget(Label(text="SEARCH STOP", font_size='30sp', size_hint_y=None, height=dp(50)))
        
        search_input = TextInput(multiline=False, font_size='24sp', size_hint_y=None, height=dp(60))
        search_input.bind(text=lambda instance, value: sett.search_stop(value))
        s_layout.add_widget(search_input)
        
        results_scroll = ScrollView()
        results_list = GridLayout(cols=1, size_hint_y=None, spacing=5)
        results_list.bind(minimum_height=results_list.setter('height'))
        results_scroll.add_widget(results_list)
        s_layout.add_widget(results_scroll)
        
        back_btn = Button(text="BACK / CANCEL", size_hint_y=None, height=dp(60))
        back_btn.bind(on_release=lambda x: setattr(sm, 'current', 'main'))
        s_layout.add_widget(back_btn)
        
        sett.add_widget(s_layout)
        sett.ids = {'search_input': search_input, 'results_list': results_list}

        sm.add_widget(main)
        sm.add_widget(sett)
        return sm

if __name__ == "__main__":
    DepartureApp().run()