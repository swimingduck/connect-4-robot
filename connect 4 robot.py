import discord
import asyncio
import random

class Client(discord.Client):
    elo_ratings = {}

    def __init__(self):
        discord.Client.__init__(self)

        with open("elo_ratings.txt", "r") as f:
            scores = f.read().split("\n")[:-1]

            for score in scores:
                score = score.split(" ")
                Client.elo_ratings[int(score[0])] = [int(score[1]), int(score[2]), int(score[3])]

    async def on_ready(self):
        print("Logged in as {}".format(self.user))

    async def on_message(self, message):
        banned_servers = [
            449184420432183297
        ]

        if message.guild.id in banned_servers:
            return

        if message.author == self.user:
            return

        if message.content.startswith("c!stats"):
            s = "```\n"

            if message.content == "c!stats":
                player_id = message.author.id
            else:
                id_index = message.content.index("<@") + 2
                if message.content[id_index] == "!":
                    id_index += 1

                player_id = int(message.content[id_index:id_index + 18])

            if player_id not in Client.elo_ratings:
                await message.channel.send(content="Player has never played before")
                return

            s += "Rank: {}\n".format(Client.elo_ratings[player_id][0])
            s += "Win rate: {}\n```".format(round(Client.elo_ratings[player_id][1] / (Client.elo_ratings[player_id][1] + Client.elo_ratings[player_id][2]), 2))

            await message.channel.send(content=s)

        if message.content.startswith("c!top"):
            page = 1

            if len(message.content.split(" ")) >= 2:
                if message.content.split(" ")[1].isdigit():
                    page = int(message.content.split(" ")[1])

            s = "```\n"

            scores = [[user] + Client.elo_ratings[user] for user in Client.elo_ratings]
            scores.sort(key=lambda x: x[1])
            scores = list(reversed(scores))

            for i in range(min(10, len(Client.elo_ratings))):
                s += "#{}: {}\n".format(i + 1, self.get_user(scores[i][0]))
                s += "Rank: {} - Win rate: {}\n\n".format(scores[i][1], round(scores[i][2] / (scores[i][2] + scores[i][3]), 2))

            s = s[:-1] + "```"

            await message.channel.send(content=s)

        if message.content.startswith("c!challenge"):
            # Sending the request to start a game
            id_index = message.content.index("<@") + 2
            if message.content[id_index] == "!":
                id_index += 1

            player1 = message.author
            player2 = self.get_user(int(message.content[id_index:id_index + 18]))
            current_player = random.choice([player1, player2])

            game_channel = message.channel
            prev_message = None

            board = [[0 for i in range(7)] for i in range(6)]

            if player1.id == player2.id:
                await game_channel.send("Nice try")
                return

            # Waiting for a response
            request = await game_channel.send(content="React with :white_check_mark: or :negative_squared_cross_mark:")

            await request.add_reaction("\U00002705")
            await request.add_reaction("\U0000274E")

            def check_reply(reaction, user):
                return (user == player2 and reaction.message.id == request.id and
                        (reaction.emoji in ["\U00002705", "\U0000274E"]))

            try:
                reaction, user = await self.wait_for("reaction_add", check=check_reply, timeout=15.0)
            except asyncio.TimeoutError:
                await game_channel.send("No response, request cancelled")
                return

            if reaction.emoji == "\U0000274E":
                await game_channel.send("Game declined")
                return

            await game_channel.send(content="<@{}> is player 1\n<@{}> is player 2".format(player1.id, player2.id))

            prev_message = await Client.send_board(board=board, game_channel=game_channel, player_num=Client.get_player_number(player1, player2, current_player), game_end=False)

            # Game loop
            while True:
                def check_reaction(reaction, user):
                    return (user == current_player and reaction.message.id == prev_message.id and
                        (reaction.emoji[0] in "1234567") and board[0][int(reaction.emoji[0]) - 1] == 0)

                try:
                    reaction, user = await self.wait_for("reaction_add", check=check_reaction, timeout=60.0)
                except asyncio.TimeoutError:
                    await game_channel.send("<@{}> wins by timeout!".format([player1, player2][current_player == player1].id))

                    Client.update_elo_ratings([player1, player2][current_player == player1].id, current_player.id)

                    return

                Client.add_piece(board=board, column=int(reaction.emoji[0]) - 1,
                                 color=Client.get_player_number(player1, player2, current_player))

                await prev_message.delete()

                game_end = Client.check_win(board, Client.get_player_number(player1, player2, current_player))

                if game_end:
                    tie = False
                else:
                    tie = True

                for row in board:
                    if 0 in row:
                        tie = False
                        break

                if tie:
                    game_end = True

                player_num = 3 - Client.get_player_number(player1, player2, current_player)
                prev_message = await Client.send_board(board=board, game_channel=game_channel, player_num=player_num, game_end=game_end)

                if tie:
                    await game_channel.send(content="Draw, no winner")

                    return

                if game_end:
                    await game_channel.send(content="<@{}> wins!".format(current_player.id))

                    Client.update_elo_ratings(current_player.id, [player1, player2][current_player == player1].id)

                    return

                current_player = [player1, player2][current_player == player1]

    @classmethod
    def update_elo_ratings(cls, winner_id, loser_id):
        # Elo K-Factor
        K = 32

        if winner_id not in cls.elo_ratings:
            cls.elo_ratings[winner_id] = [cls.get_avg_elo(), 0, 0]

        if loser_id not in cls.elo_ratings:
            cls.elo_ratings[loser_id] = [cls.get_avg_elo(), 0, 0]

        t1 = cls.elo_ratings[winner_id]
        t2 = cls.elo_ratings[loser_id]

        R1 = pow(10, t1[0] / 400)
        R2 = pow(10, t2[0] / 400)

        E1 = R1 / (R1 + R2)
        E2 = R2 / (R1 + R2)

        S1 = 1
        S2 = 0

        r1 = t1[0] + K * (S1 - E1)
        r2 = t2[0] + K * (S2 - E2)

        t1[0] = round(r1)
        t2[0] = round(r2)

        t1[1] += 1
        t2[2] += 1

        cls.elo_ratings[winner_id] = t1
        cls.elo_ratings[loser_id] = t2

        cls.save_elo_ratings()

        return

    @classmethod
    def save_elo_ratings(cls):
        s = ""

        for player in cls.elo_ratings:
            s += "{} {} {} {}\n".format(player, cls.elo_ratings[player][0], cls.elo_ratings[player][1], cls.elo_ratings[player][2])

        with open("elo_ratings.txt", "w") as f:
            f.write(s)

    @staticmethod
    async def send_board(board, game_channel, player_num, game_end):
        if game_end:
            message = "Game end\n\n"
        else:
            if player_num == 1:
                message = ":red_circle: Player 1's turn\n\n"
            elif player_num == 2:
                message = ":yellow_circle: Player 2's turn\n\n"

        for row, line in enumerate(board):
            message += " "

            for column, piece in enumerate(line):
                if piece == 0:
                    message += ":black_circle:"
                elif piece == 1:
                    message += ":red_circle:"
                elif piece == 2:
                    message += ":yellow_circle:"

                if column != 6:
                    message += ":blue_square:"

            if row != 5:
                message += "\n " + ":blue_square:" * 13 + "\n"

        prev_message = await game_channel.send(content=message)

        for i in range(1, 8):
            await prev_message.add_reaction("{}\N{COMBINING ENCLOSING KEYCAP}".format(i))

        return prev_message

    @classmethod
    def get_avg_elo(cls):
        return 1000

        total = 0

        for player in cls.elo_ratings:
            total += cls.elo_ratings[player][0]

        return round(total / len(cls.elo_ratings))

    @staticmethod
    def get_player_number(player1, player2, player):
        if player == player1:
            return 1
        elif player == player2:
            return 2

    @staticmethod
    def add_piece(board, column, color):
        for i in range(1, 6):
            if board[i][column] != 0:
                board[i - 1][column] = color
                break
        else:
            board[5][column] = color

    @staticmethod
    def check_win(board, color):
        for row in range(6):
            score = 0

            for column in range(7):
                if board[row][column] == color:
                    score += 1
                else:
                    score = 0

                if score == 4:
                    return True

        for column in range(7):
            score = 0

            for row in range(6):
                if board[row][column] == color:
                    score += 1
                else:
                    score = 0

                if score == 4:
                    return True

        for row in range(3):
            for column in range(4):
                score = 0

                i = 0
                while row + i < 6 and column + i < 7:
                    if board[row + i][column + i] == color:
                        score += 1
                    else:
                        score = 0

                    if score == 4:
                        return True

                    i += 1

        for row in range(3, 6):
            for column in range(4):
                score = 0

                i = 0
                while row - i > -1 and column + i < 7:
                    if board[row - i][column + i] == color:
                        score += 1
                    else:
                        score = 0

                    if score == 4:
                        return True

                    i += 1

        return False



client = Client()
client.run(token)
