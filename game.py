import math
import random
import sys
from pathlib import Path

import pygame


WIDTH, HEIGHT = 1180, 700
FPS = 60
LANE_Y = (285, 380, 475)
BACKGROUND = (12, 17, 30)
FONT_NAME = "dejavusans"
ROOT = Path(__file__).resolve().parent
TRACK_DIR = ROOT / "tracks"
AUDIO_EXTENSIONS = {".wav", ".ogg", ".mp3", ".flac"}
THEMES = (
	{"name": "CYBER", "lanes": ((73, 207, 190), (255, 190, 79), (255, 103, 137)),
	 "background": (12, 17, 30), "surface": (20, 29, 47), "border": (50, 68, 91),
	 "text": (235, 242, 255), "muted": (142, 157, 180), "accent": (255, 224, 144),
	 "button": (73, 207, 190), "ink": (8, 24, 31)},
	{"name": "LASER", "lanes": ((83, 166, 255), (255, 82, 175), (181, 105, 255)),
	 "background": (22, 10, 35), "surface": (42, 20, 62), "border": (91, 46, 112),
	 "text": (245, 235, 255), "muted": (181, 145, 202), "accent": (255, 166, 224),
	 "button": (255, 82, 175), "ink": (35, 8, 30)},
	{"name": "SYNTH", "lanes": ((255, 111, 91), (255, 215, 83), (117, 231, 122)),
	 "background": (31, 19, 12), "surface": (57, 34, 18), "border": (112, 76, 35),
	 "text": (255, 246, 222), "muted": (198, 164, 119), "accent": (255, 215, 83),
	 "button": (117, 231, 122), "ink": (15, 38, 20)},
)


def clamp(value, low, high):
	return max(low, min(high, value))


def draw_text(surface, font, text, position, color=(235, 242, 255), anchor="topleft"):
	image = font.render(text, True, color)
	rectangle = image.get_rect()
	setattr(rectangle, anchor, position)
	surface.blit(image, rectangle)
	return rectangle


def scan_tracks():
	TRACK_DIR.mkdir(exist_ok=True)
	return sorted(
		(path for path in TRACK_DIR.iterdir() if path.suffix.lower() in AUDIO_EXTENSIONS),
		key=lambda path: path.name.lower(),
	)


def open_track_dialog():
	try:
		import tkinter as tk
		from tkinter import filedialog

		root = tk.Tk()
		root.withdraw()
		selected = filedialog.askopenfilename(
			title="Выберите музыкальный трек",
			filetypes=[("Аудио", "*.wav *.ogg *.mp3 *.flac"), ("Все файлы", "*.*")],
		)
		root.destroy()
		return Path(selected) if selected else None
	except Exception:
		return None


class Note:
	def __init__(self, lane, x, speed, color):
		self.lane = lane
		self.x = x
		self.previous_x = x
		self.speed = speed
		self.color = color
		self.hit = False
		self.missed = False

	@property
	def y(self):
		return LANE_Y[self.lane]

	@property
	def hitbox(self):
		return pygame.Rect(int(self.x - 18), self.y - 18, 36, 36)

	def update(self, dt):
		self.previous_x = self.x
		self.x -= self.speed * dt

	def draw(self, surface, pulse):
		if self.hit:
			return
		radius = 15 + int(pulse * 3)
		points = ((self.x, self.y - radius), (self.x + radius, self.y),
				  (self.x, self.y + radius), (self.x - radius, self.y))
		glow = pygame.Surface((90, 90), pygame.SRCALPHA)
		for glow_radius, alpha in ((28, 18), (23, 27), (19, 40)):
			pygame.draw.circle(glow, (*self.color, alpha), (45, 45), glow_radius)
		surface.blit(glow, (self.x - 45, self.y - 45))
		pygame.draw.polygon(surface, self.color, points)
		pygame.draw.polygon(surface, (255, 255, 255), points, 2)
		pygame.draw.line(surface, (255, 255, 255), (self.x - 5, self.y - 5), (self.x + 5, self.y + 5), 2)


class Game:
	def __init__(self):
		pygame.init()
		pygame.mixer.init()
		self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
		pygame.display.set_caption("Rhythm Lines")
		self.clock = pygame.time.Clock()
		self.font_small = pygame.font.SysFont(FONT_NAME, 17)
		self.font = pygame.font.SysFont(FONT_NAME, 23)
		self.font_big = pygame.font.SysFont(FONT_NAME, 43, bold=True)
		self.font_huge = pygame.font.SysFont(FONT_NAME, 70, bold=True)
		self.running = True
		self.mode = "menu"
		self.difficulties = (("EASY", 0.92, 72), ("NORMAL", 0.70, 112), ("HARD", 0.48, 158))
		self.difficulty = 1
		self.volume = 0.65
		self.theme_index = 0
		self.speed_factor = 1.0
		self.tracks = scan_tracks()
		self.track_index = 0
		self.notes = []
		self.player_lane = 1
		self.score = 0
		self.combo = 0
		self.best_combo = 0
		self.misses = 0
		self.song_time = 0.0
		self.note_timer = 0.0
		self.background_offset = 0.0
		self.flash = 0.0
		self.message = ""
		self.pause_started = 0
		pygame.mixer.music.set_volume(self.volume)

	@property
	def lane_colors(self):
		return THEMES[self.theme_index]["lanes"]

	@property
	def theme(self):
		return THEMES[self.theme_index]

	@property
	def selected_track(self):
		return self.tracks[self.track_index] if self.tracks else None

	@property
	def difficulty_data(self):
		return self.difficulties[self.difficulty]

	@property
	def player_hitbox(self):
		return pygame.Rect(91, LANE_Y[self.player_lane] - 25, 48, 50)

	def run(self):
		while self.running:
			dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
			self.handle_events()
			if self.mode == "game":
				self.update_game(dt)
			self.draw()
		pygame.quit()

	def handle_events(self):
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				self.running = False
			elif event.type == pygame.KEYDOWN:
				self.handle_key(event.key)
			elif event.type == pygame.MOUSEBUTTONDOWN and self.mode in ("menu", "settings", "game"):
				self.handle_menu_click(event.pos)

	def handle_key(self, key):
		if key == pygame.K_ESCAPE:
			if self.mode == "game":
				self.finish_game()
			elif self.mode == "settings":
				self.mode = "menu"
			else:
				self.running = False
		elif self.mode == "menu":
			if key in (pygame.K_LEFT, pygame.K_a):
				self.track_index = (self.track_index - 1) % max(1, len(self.tracks))
			elif key in (pygame.K_RIGHT, pygame.K_d):
				self.track_index = (self.track_index + 1) % max(1, len(self.tracks))
			elif key in (pygame.K_UP, pygame.K_DOWN):
				self.difficulty = (self.difficulty + (1 if key == pygame.K_DOWN else -1)) % 3
			elif key == pygame.K_RETURN:
				self.start_game()
			elif key == pygame.K_o:
				selected = open_track_dialog()
				if selected and selected.exists() and selected not in self.tracks:
					self.tracks.append(selected)
					self.track_index = len(self.tracks) - 1
		elif self.mode == "settings":
			if key in (pygame.K_LEFT, pygame.K_RIGHT):
				self.theme_index = (self.theme_index + (1 if key == pygame.K_RIGHT else -1)) % len(THEMES)
			elif key == pygame.K_ESCAPE or key == pygame.K_RETURN:
				self.mode = "menu"
		elif self.mode == "game":
			if key in (pygame.K_1, pygame.K_2, pygame.K_3):
				self.player_lane = key - pygame.K_1
			elif key in (pygame.K_p, pygame.K_SPACE):
				self.toggle_pause()
		elif self.mode == "paused" and key in (pygame.K_p, pygame.K_SPACE):
			self.toggle_pause()

	def handle_menu_click(self, position):
		x, y = position
		if self.mode == "settings":
			if 430 <= x <= 750 and 220 <= y <= 290:
				self.theme_index = (self.theme_index + 1) % len(THEMES)
			elif 450 <= x <= 730 and 340 <= y <= 430:
				self.speed_factor = clamp(0.55 + (x - 450) / 280 * 1.10, 0.55, 1.65)
			elif 430 <= x <= 750 and 545 <= y <= 600:
				self.mode = "menu"
			return
		if self.mode == "game":
			if 1060 <= x <= 1140 and 20 <= y <= 70:
				self.toggle_pause()
			return
		if 430 <= x <= 750 and 515 <= y <= 573:
			self.start_game()
		elif 430 <= x <= 750 and 590 <= y <= 640:
			self.mode = "settings"
		elif 420 <= x <= 760 and 315 <= y <= 360:
			self.difficulty = (self.difficulty + 1) % 3
		elif 490 <= x <= 690 and 405 <= y <= 430:
			self.volume = clamp((x - 490) / 200, 0.0, 1.0)
			pygame.mixer.music.set_volume(self.volume)
		elif 300 <= x <= 880 and 165 <= y <= 215 and self.tracks:
			self.track_index = (self.track_index + (1 if x > 590 else -1)) % len(self.tracks)

	def start_game(self):
		self.mode = "game"
		self.notes.clear()
		self.player_lane = 1
		self.score = 0
		self.combo = 0
		self.best_combo = 0
		self.misses = 0
		self.song_time = 0.0
		self.note_timer = 0.4
		self.flash = 0.0
		self.message = ""
		if self.selected_track:
			try:
				pygame.mixer.music.load(str(self.selected_track))
				pygame.mixer.music.play()
			except pygame.error:
				self.message = "Не удалось открыть файл, запущен тренировочный ритм"

	def finish_game(self):
		pygame.mixer.music.stop()
		self.mode = "menu"

	def toggle_pause(self):
		if self.mode == "game":
			self.mode = "paused"
			pygame.mixer.music.pause()
		else:
			self.mode = "game"
			pygame.mixer.music.unpause()

	def update_game(self, dt):
		self.song_time += dt
		self.background_offset = (self.background_offset + dt * 42) % 80
		self.flash = max(0.0, self.flash - dt)
		spacing, speed = self.difficulty_data[1:]
		speed *= self.speed_factor
		self.note_timer -= dt
		if self.note_timer <= 0:
			lane = random.randrange(3)
			self.notes.append(Note(lane, WIDTH + 35, speed, self.lane_colors[lane]))
			self.note_timer = spacing + random.uniform(-0.10, 0.12)
		for note in self.notes:
			note.update(dt)
			if not note.hit and not note.missed and note.lane == self.player_lane and note.hitbox.colliderect(self.player_hitbox):
				note.hit = True
				self.score += 100 + self.combo * 10
				self.combo += 1
				self.best_combo = max(self.best_combo, self.combo)
				self.flash = 0.16
			elif not note.hit and not note.missed and note.x < 85:
				note.missed = True
				self.misses += 1
				self.combo = 0
		self.notes = [note for note in self.notes if note.x > -50 and not note.hit]

	def draw(self):
		self.screen.fill(self.theme["background"])
		self.draw_background()
		if self.mode == "menu":
			self.draw_menu()
		elif self.mode == "settings":
			self.draw_settings()
		else:
			self.draw_game()
		pygame.display.flip()

	def draw_background(self):
		for y in range(0, HEIGHT, 2):
			base = self.theme["background"]
			shade = tuple(min(255, channel + int(y / HEIGHT * 10)) for channel in base)
			pygame.draw.line(self.screen, shade, (0, y), (WIDTH, y))
		for x in range(-80, WIDTH + 80, 80):
			pygame.draw.line(self.screen, self.theme["border"], (x + self.background_offset, 0),
							 (x - 180 + self.background_offset, HEIGHT), 1)

	def draw_menu(self):
		draw_text(self.screen, self.font_small, "RHYTHM LINES / MUSIC ARCADE", (WIDTH // 2, 72), self.lane_colors[0], "midtop")
		draw_text(self.screen, self.font_huge, "ЛИНИИ РИТМА", (WIDTH // 2, 110), self.theme["text"], "midtop")
		panel = pygame.Rect(290, 165, 600, 320)
		pygame.draw.rect(self.screen, self.theme["surface"], panel, border_radius=8)
		pygame.draw.rect(self.screen, self.theme["border"], panel, 2, border_radius=8)
		draw_text(self.screen, self.font_small, "ТРЕК  <  A / D  >", (WIDTH // 2, 178), self.theme["muted"], "midtop")
		track_name = self.selected_track.stem if self.selected_track else "Тренировочный ритм"
		draw_text(self.screen, self.font_big, track_name[:28], (WIDTH // 2, 198), self.theme["accent"], "midtop")
		draw_text(self.screen, self.font_small, "O  открыть аудиофайл", (WIDTH // 2, 254), self.theme["muted"], "midtop")
		difficulty_name = self.difficulty_data[0]
		draw_text(self.screen, self.font, f"СЛОЖНОСТЬ: {difficulty_name}   (стрелки вверх/вниз)", (WIDTH // 2, 320), self.theme["text"], "midtop")
		draw_text(self.screen, self.font_small, "ГРОМКОСТЬ МУЗЫКИ", (WIDTH // 2, 389), self.theme["muted"], "midtop")
		pygame.draw.rect(self.screen, self.theme["border"], (490, 414, 200, 7), border_radius=4)
		pygame.draw.rect(self.screen, self.theme["button"], (490, 414, int(200 * self.volume), 7), border_radius=4)
		pygame.draw.circle(self.screen, self.theme["accent"], (490 + int(200 * self.volume), 417), 10)
		button = pygame.Rect(430, 515, 320, 58)
		pygame.draw.rect(self.screen, self.theme["button"], button, border_radius=6)
		draw_text(self.screen, self.font_big, "ИГРАТЬ", button.center, self.theme["ink"], "center")
		settings_button = pygame.Rect(430, 590, 320, 42)
		pygame.draw.rect(self.screen, self.theme["surface"], settings_button, border_radius=6)
		draw_text(self.screen, self.font, "НАСТРОЙКИ", settings_button.center, self.theme["text"], "center")
		draw_text(self.screen, self.font_small, "ENTER / клик   |   ESC выход", (WIDTH // 2, 655), self.theme["muted"], "midtop")
		if self.message:
			draw_text(self.screen, self.font_small, self.message, (WIDTH // 2, 650), (255, 149, 132), "midtop")

	def draw_game(self):
		draw_text(self.screen, self.font_small, "RHYTHM LINES", (38, 28), self.lane_colors[0])
		draw_text(self.screen, self.font, f"SCORE  {self.score:06d}", (930, 25), self.theme["accent"], "topright")
		draw_text(self.screen, self.font_small, f"COMBO  {self.combo}     MISS  {self.misses}", (930, 57), self.theme["muted"], "topright")
		draw_text(self.screen, self.font_small, "1     2     3", (115, 212), self.theme["text"], "midtop")
		for index, y in enumerate(LANE_Y):
			color = self.lane_colors[index]
			pygame.draw.line(self.screen, self.theme["surface"], (60, y), (WIDTH - 55, y), 10)
			pygame.draw.line(self.screen, color, (60, y), (WIDTH - 55, y), 2)
			pygame.draw.circle(self.screen, color, (68, y), 4)
			if index == self.player_lane:
				glow = pygame.Surface((100, 100), pygame.SRCALPHA)
				pygame.draw.circle(glow, (*color, 42), (50, 50), 34)
				self.screen.blit(glow, (65, y - 50))
				player_points = ((115, y - 26), (142, y), (115, y + 26), (88, y))
				pygame.draw.polygon(self.screen, (255, 245, 203), player_points)
				pygame.draw.polygon(self.screen, color, player_points, 4)
				pygame.draw.circle(self.screen, (255, 255, 255), (110, y - 5), 4)
		pygame.draw.line(self.screen, self.theme["accent"], (115, LANE_Y[0] - 40), (115, LANE_Y[2] + 40), 1)
		pulse = (math.sin(self.song_time * 8) + 1) / 2
		for note in self.notes:
			note.draw(self.screen, pulse)
		pause_button = pygame.Rect(1060, 20, 80, 50)
		pygame.draw.rect(self.screen, self.theme["surface"], pause_button, border_radius=6)
		draw_text(self.screen, self.font, "II", pause_button.center, self.theme["accent"], "center")
		draw_text(self.screen, self.font_small, f"SPEED  {self.speed_factor:.2f}x", (38, 615), self.lane_colors[0])
		draw_text(self.screen, self.font_small, "Лови ноты ромбиком   |   P / SPACE: пауза   |   ESC: меню", (WIDTH // 2, HEIGHT - 38), self.theme["muted"], "midtop")
		if self.flash:
			overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
			overlay.fill((255, 242, 183, int(self.flash * 140)))
			self.screen.blit(overlay, (0, 0))
		if self.mode == "paused":
			overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
			overlay.fill((5, 8, 18, 175))
			self.screen.blit(overlay, (0, 0))
			draw_text(self.screen, self.font_huge, "ПАУЗА", (WIDTH // 2, 270), self.theme["accent"], "midtop")
			draw_text(self.screen, self.font, "P / SPACE продолжить", (WIDTH // 2, 365), self.lane_colors[0], "midtop")

	def draw_settings(self):
		draw_text(self.screen, self.font_small, "RHYTHM LINES / SETTINGS", (WIDTH // 2, 75), self.lane_colors[0], "midtop")
		draw_text(self.screen, self.font_huge, "НАСТРОЙКИ", (WIDTH // 2, 112), (244, 247, 255), "midtop")
		panel = pygame.Rect(290, 185, 600, 330)
		pygame.draw.rect(self.screen, self.theme["surface"], panel, border_radius=8)
		pygame.draw.rect(self.screen, self.theme["border"], panel, 2, border_radius=8)
		draw_text(self.screen, self.font_small, "НЕОНОВАЯ ТЕМА (влево/вправо или клик)", (WIDTH // 2, 215), self.theme["muted"], "midtop")
		draw_text(self.screen, self.font_big, self.theme["name"], (WIDTH // 2, 245), self.lane_colors[1], "midtop")
		for index, color in enumerate(self.lane_colors):
			pygame.draw.circle(self.screen, color, (510 + index * 80, 310), 17)
		draw_text(self.screen, self.font_small, "СКОРОСТЬ ДОРОЖКИ", (WIDTH // 2, 355), self.theme["muted"], "midtop")
		pygame.draw.rect(self.screen, self.theme["border"], (450, 390, 280, 7), border_radius=4)
		pygame.draw.rect(self.screen, self.lane_colors[0], (450, 390, int(280 * (self.speed_factor - 0.55) / 1.10), 7), border_radius=4)
		pygame.draw.circle(self.screen, self.theme["accent"], (450 + int(280 * (self.speed_factor - 0.55) / 1.10), 393), 10)
		draw_text(self.screen, self.font, f"{self.speed_factor:.2f}x", (WIDTH // 2, 420), self.theme["accent"], "midtop")
		button = pygame.Rect(430, 545, 320, 55)
		pygame.draw.rect(self.screen, self.lane_colors[0], button, border_radius=6)
		draw_text(self.screen, self.font, "НАЗАД  (ENTER / ESC)", button.center, self.theme["ink"], "center")


if __name__ == "__main__":
	try:
		Game().run()
	except pygame.error as error:
		print(f"Не удалось запустить pygame: {error}", file=sys.stderr)
		sys.exit(1)
