class Settings():
    def __init__(self):
        self.game_folder = ""

    def set_game_folder(self, game_folder):
        self.game_folder = game_folder

    def get_game_folder(self):
        return self.game_folder