import os
import json
import requests
import threading
from datetime import datetime, timezone

# --- 1. KIVY CONFIGURATION ---
from kivy.config import Config
Config.set('graphics', 'fullscreen', '1')
Config.set('graphics', 'show_cursor', '0')
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '480')
Config.set('input', 'mouse', 'none')
Config.set('input', 'hidinput', 'hidinput')
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

def get_line_color(line, mode):
    mode = mode.lower()
    if mode == 'metro':
        metro_colors = {"1": (0.92, 0.44, 0.05, 1), "2": (0.90, 0, 0, 1), "3": (0.66, 0, 0.42, 1), "4": (0, 0.27, 0.58, 1), "5": (0, 0.56, 0.23, 1)}
        return metro_colors.get(line, (0.4, 0.4, 0.4, 1))
    if mode == 'tram': return (0.00, 0.35, 0.70, 1)
    if mode == 'rail': return (0.00, 0.20, 0.40, 1)
    if mode == 'water': return (0.00, 0.65, 0.85, 1)
    if mode == 'bus':
        if len(line) >= 3 or line.startswith(('1', '2', '3', '4', '5')):
            return (0.00, 0.55, 0.25, 1) if len(line) != 2 else (0.90, 0, 0, 1)
        return (0.90, 0.00, 0.00, 1)
    return (0.3, 0.3, 0.3, 1)

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return f"{int(f.read()) / 1000:.1f}°C"
    except: return "??°C"

class DataStore:
    def __init__(self): self.cfg = self.load_config()
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
    def __init__(self, line, dest, time_str, aimed_str, is_delayed, is_cancelled, mins, mode, is_single, **kwargs):
        # Configuration for sizing
        self.row_h = dp(85) if is_single else dp(55)
        self.font_dest = '28sp' if is_single else '17sp'
        self.font_time = '32sp' if is_single else '20sp'
        self.font_line = '26sp' if is_single else '16sp'
        
        # INCREASED FONT SIZES FOR STRIKE-THROUGH TIME HERE:
        self.font_aimed = '20sp' if is_single else '14sp' 
        
        self.pill_w = dp(90) if is_single else dp(55)
        self.pill_h = dp(55) if is_single else dp(34)
        self.time_w = dp(160) if is_single else dp(95)

        super().__init__(orientation='horizontal', size_hint_y=None, height=self.row_h, padding=[dp(10), 0], **kwargs)
        
        with self.canvas.before:
            self.bg_color = Color(0.12, 0.12, 0.12, 1) if mins <= 1 and not is_cancelled else Color(0, 0, 0, 0)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
            Color(0.25, 0.25, 0.25, 1)
            self.border = Rectangle(pos=(self.x, self.y), size=(self.width, dp(1)))
        self.bind(pos=self._update_graphics, size=self._update_graphics)

        # 1. Line Pill Container
        pill_box = BoxLayout(size_hint_x=None, width=self.pill_w)
        line_color = get_line_color(line, mode)
        with pill_box.canvas.before:
            Color(*line_color)
            self.pill_rect = RoundedRectangle(size=(self.pill_w - dp(10), self.pill_h), radius=[dp(6)])
        pill_box.bind(pos=self._update_pill, size=self._update_pill)
        
        # Line Number Label
        self.line_lbl = Label(text=line, bold=True, font_size=self.font_line, halign='center', valign='middle')
        self.line_lbl.bind(size=self._update_text_size)
        pill_box.add_widget(self.line_lbl)
        self.add_widget(pill_box)

        # 2. Destination Label
        self.dest_label = Label(text=dest.upper(), font_size=self.font_dest, halign='left', valign='middle', 
                               shorten=True, shorten_from='right', padding=[dp(15), 0])
        self.dest_label.bind(size=self._update_text_size)
        self.add_widget(self.dest_label)

        # 3. Time Column
        time_col = BoxLayout(orientation='vertical', size_hint_x=None, width=self.time_w, padding=[0, dp(2)])
        
        if is_cancelled:
            self.time_lbl = Label(text="INNSTILT", font_size='18sp' if is_single else '14sp', bold=True, color=(1, 0.2, 0.2, 1), halign='right', valign='middle')
            self.time_lbl.bind(size=self._update_text_size)
            time_col.add_widget(self.time_lbl)
        else:
            # Main estimated time
            self.time_lbl = Label(text=time_str, font_size=self.font_time, bold=True, halign='right', valign='bottom' if is_delayed else 'middle')
            self.time_lbl.bind(size=self._update_text_size)
            time_col.add_widget(self.time_lbl)
            
            if is_delayed:
                # The aimed (original) time with strikethrough
                self.aimed_lbl = Label(
                    text=aimed_str, 
                    font_size=self.font_aimed, 
                    color=(1, 1, 1, 0.4), 
                    strikethrough=True, 
                    halign='right', 
                    valign='top', 
                    size_hint_y=0.6
                )
                self.aimed_lbl.bind(size=self._update_text_size)
                time_col.add_widget(self.aimed_lbl)
            
        self.add_widget(time_col)

    def _update_graphics(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size
        self.border.pos = instance.pos
        self.border.size = (instance.width, dp(1))

    def _update_text_size(self, instance, value):
        instance.text_size = value

    def _update_pill(self, instance, value):
        rw, rh = self.pill_rect.size
        self.pill_rect.pos = (instance.x + (instance.width - rw)/2, instance.y + (instance.height - rh)/2)

class PlatformWidget(BoxLayout):
    def __init__(self, platform_label, calls, on_click=None, **kwargs):
        content_height = dp(35) + (len(calls[:store.cfg['max_per_quay']]) * dp(50)) + dp(10)
        super().__init__(orientation='vertical', size_hint_y=None, height=content_height, **kwargs)
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.border = Line(rectangle=(self.x, self.y, self.width, self.height), width=1)
        self.bind(pos=self._update_border, size=self._update_border)

        header_btn = Button(text=f"PLATFORM {platform_label}", size_hint_y=None, height=dp(35), 
                            bold=True, font_size='14sp', background_normal='', background_color=(1, 1, 1, 0.15))
        if on_click:
            header_btn.bind(on_release=lambda x: on_click(platform_label))
        self.add_widget(header_btn)

        now = datetime.now(timezone.utc)
        for c in calls[:store.cfg['max_per_quay']]:
            expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
            aimed = datetime.fromisoformat(c["aimedDepartureTime"].replace("Z", "+00:00"))
            mins = int((expected - now).total_seconds() / 60)
            t_str = "NÅ" if mins <= 0 else f"{mins} MIN" if mins < 20 else expected.strftime("%H:%M")
            delayed = abs((expected - aimed).total_seconds()) > 60
            cancelled = c.get("predictionInaccurate", False) or c.get("status") == "cancelled"
            self.add_widget(DepartureRow(c["serviceJourney"]["line"]["publicCode"], c["destinationDisplay"]["frontText"], t_str, aimed.strftime("%H:%M"), delayed, cancelled, mins, c["serviceJourney"]["transportMode"]))

    def _update_border(self, instance, value): self.border.rectangle = (instance.x, instance.y, instance.width, instance.height)

# --- 4. SCREENS ---

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.filtered_quay = None
        self.last_data = []
        
        self.layout = BoxLayout(orientation='vertical')
        
        # Header
        header = BoxLayout(size_hint_y=None, height=dp(70), padding=[dp(15), 0], spacing=dp(10))
        with header.canvas.after:
            Color(1, 1, 1, 1)
            self.line = Rectangle(pos=(0, 0), size=(Window.width, dp(2)))
        header.bind(pos=self._update_line, size=self._update_line)

        self.stop_name = Label(text="---", font_size='22sp', bold=True, halign='left', size_hint_x=0.4)
        self.clock = Label(text="00:00", font_size='34sp', bold=True, size_hint_x=0.2)
        
        # Actions Container
        self.actions = BoxLayout(size_hint_x=0.4, spacing=dp(10), padding=[0, dp(10)])
        self.temp = Label(text="--°C", color=(0.7,0.7,0.7,1), size_hint_x=0.4)
        
        # The Back Button is created but NOT added yet
        self.btn_back_all = Button(text="BACK", bold=True, background_color=(0, 0.4, 0.8, 1), size_hint_x=0.6)
        self.btn_back_all.bind(on_release=self.reset_filter)
        
        self.btn_cfg = Button(text="CONFIG", bold=True, background_color=(0.2, 0.2, 0.2, 1))
        self.btn_exit = Button(text="X", bold=True, size_hint_x=None, width=dp(50), background_color=(0.6, 0.1, 0.1, 1))
        
        self.actions.add_widget(self.temp)
        self.actions.add_widget(self.btn_cfg)
        self.actions.add_widget(self.btn_exit)
        
        header.add_widget(self.stop_name)
        header.add_widget(self.clock)
        header.add_widget(self.actions)
        
        # Board
        self.scroll = ScrollView(do_scroll_x=False, do_scroll_y=True, bar_width=dp(5))
        self.board_grid = GridLayout(cols=2, size_hint_y=None, spacing=dp(10), padding=dp(5))
        self.board_grid.bind(minimum_height=self.board_grid.setter('height'))
        
        self.scroll.add_widget(self.board_grid)
        self.layout.add_widget(header)
        self.layout.add_widget(self.scroll)
        self.add_widget(self.layout)

    def _update_line(self, instance, value): self.line.pos = (instance.x, instance.y); self.line.size = (instance.width, dp(2))

    def reset_filter(self, *args):
        self.filtered_quay = None
        # Safely remove the back button if it exists in the layout
        if self.btn_back_all in self.actions.children:
            self.actions.remove_widget(self.btn_back_all)
        self.update_ui(self.last_data)

    def filter_to_quay(self, quay_label):
        self.filtered_quay = quay_label
        # Add the back button to the actions layout if not already there
        if self.btn_back_all not in self.actions.children:
            # Insert it before the Config button (index 1)
            self.actions.add_widget(self.btn_back_all, index=2)
        self.update_ui(self.last_data)

    def on_enter(self):
        Clock.schedule_interval(self.tick, 1)
        self.fetch_data()
        Clock.schedule_interval(lambda dt: self.fetch_data(), 20)

    def tick(self, dt): self.clock.text = datetime.now().strftime("%H:%M"); self.temp.text = get_cpu_temp()
    def fetch_data(self): threading.Thread(target=self._query, daemon=True).start()

    def _query(self):
        q = f'''{{
          stopPlace(id: "{store.cfg['stop_id']}") {{
            estimatedCalls(numberOfDepartures: 50) {{
              aimedDepartureTime
              expectedDepartureTime
              predictionInaccurate
              quay {{ id publicCode name }}
              destinationDisplay {{ frontText }}
              serviceJourney {{ transportMode line {{ publicCode }} }}
            }}
          }}
        }}'''
        try:
            r = requests.post("https://api.entur.io/journey-planner/v3/graphql", headers={"ET-Client-Name": "raspi-kivy"}, json={"query": q}, timeout=5)
            self.last_data = r.json()["data"]["stopPlace"]["estimatedCalls"]
            Clock.schedule_once(lambda dt: self.update_ui(self.last_data))
        except: pass

    def update_ui(self, calls):
        self.stop_name.text = store.cfg['stop_name'].upper()
        self.board_grid.clear_widgets()
        self.board_grid.cols = 2 if not self.filtered_quay else 1
        
        grouped = {}
        now = datetime.now(timezone.utc)
        for c in calls:
            expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
            if 0 <= (expected - now).total_seconds() <= 3600:
                q_info = c.get("quay", {})
                p_label = q_info.get("publicCode") or q_info.get("name", "").replace(store.cfg['stop_name'], "").strip()
                if not p_label or len(p_label) > 5: p_label = q_info.get("id", "??").split(":")[-1]
                
                if self.filtered_quay and p_label != self.filtered_quay: continue
                grouped.setdefault(p_label, []).append(c)

        for p_label in sorted(grouped.keys()):
            self.board_grid.add_widget(PlatformWidget(p_label, grouped[p_label], on_click=self.filter_to_quay))

class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(30), spacing=dp(15))
        layout.add_widget(Label(text="SEARCH STOP", font_size='24sp', bold=True, size_hint_y=None, height=dp(40)))
        self.inp = TextInput(multiline=False, font_size='28sp', size_hint_y=None, height=dp(60), background_color=(0.1,0.1,0.1,1), foreground_color=(1,1,1,1), keyboard_suggestions=False)
        self.inp.bind(text=self.on_search)
        layout.add_widget(self.inp)
        self.results = GridLayout(cols=1, size_hint_y=None, spacing=dp(5))
        self.results.bind(minimum_height=self.results.setter('height'))
        scroll = ScrollView(); scroll.add_widget(self.results)
        layout.add_widget(scroll)
        self.btn_back = Button(text="CANCEL", size_hint_y=None, height=dp(60))
        layout.add_widget(self.btn_back); self.add_widget(layout)
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

class DepartureApp(App):
    def build(self):
        sm = ScreenManager(transition=NoTransition())
        self.main = MainScreen(name='main'); self.sett = SettingsScreen(name='settings')
        self.main.btn_cfg.bind(on_release=lambda x: setattr(sm, 'current', 'settings'))
        self.main.btn_exit.bind(on_release=lambda x: os._exit(0))
        self.sett.btn_back.bind(on_release=lambda x: setattr(sm, 'current', 'main'))
        sm.add_widget(self.main); sm.add_widget(self.sett)
        return sm

if __name__ == "__main__": DepartureApp().run()