import socket
import sys
import threading
import Channel
import User
import Util
import time

class Server:
    SERVER_CONFIG = {"MAX_CONNECTIONS": 15}

    HELP_MESSAGE = """\n> The list of commands available are:

/help                   - Show the instructions
/join [channel_name]    - To create or switch to a channel.
/quit                   - Exits the program.
/list                   - Lists all available channels.
/time                   - Returns the local time on the current server\n\n""".encode('utf8')

    WELCOME_MESSAGE = "\n> Welcome to our chat app!!! What is your name?\n".encode('utf8')

    def __init__(self, host=socket.gethostbyname('localhost'), port=50000, allowReuseAddress=True, timeout=1000):
        self.address = (host, port)
        self.channels = {} # Channel Name -> Channel
        self.users_channels_map = {} # User Name -> Channel Name
        self.client_thread_list = [] # A list of all threads that are either running or have finished their task.
        self.users = [] # A list of all the users who are connected to the server.
        self.exit_signal = threading.Event()

        try:
            self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as errorMessage:
            sys.stderr.write("Failed to initialize the server. Error - {0}".format(errorMessage))
            raise

        self.serverSocket.settimeout(timeout)

        if allowReuseAddress:
            self.serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.serverSocket.bind(self.address)
        except socket.error as errorMessage:
            sys.stderr.write('Failed to bind to address {0} on port {1}. Error - {2}'.format(self.address[0], self.address[1], errorMessage))
            raise

    def start_listening(self, defaultGreeting="\n> Welcome to our chat app!!! What is your full name?\n"):
        self.serverSocket.listen(Server.SERVER_CONFIG["MAX_CONNECTIONS"])

        try:
            while not self.exit_signal.is_set():
                try:
                    print("Waiting for a client to establish a connection\n")
                    clientSocket, clientAddress = self.serverSocket.accept()
                    print("Connection established with IP address {0} and port {1}\n".format(clientAddress[0], clientAddress[1]))
                    user = User.User(clientSocket)
                    self.users.append(user)
                    self.welcome_user(user)
                    clientThread = threading.Thread(target=self.client_thread, args=(user,))
                    clientThread.start()
                    self.client_thread_list.append(clientThread)
                except socket.timeout:
                    pass
        except KeyboardInterrupt:
            self.exit_signal.set()

        for client in self.client_thread_list:
            if client.is_alive():
                client.join()

    def welcome_user(self, user):
        user.socket.sendall(Server.WELCOME_MESSAGE)

    def client_thread(self, user, size=4096):
        username = Util.generate_username(user.socket.recv(size).decode('utf8')).lower()

        while not username:
            user.socket.sendall("\n> Please enter your full name(first and last. middle optional).\n".encode('utf8'))
            username = Util.generate_username(user.socket.recv(size).decode('utf8')).lower()

        user.username = username

        welcomeMessage = '\n> Welcome {0}, type /help for a list of helpful commands.\n\n'.format(user.username).encode('utf8')
        user.socket.sendall(welcomeMessage)

        while True:
            chatMessage = user.socket.recv(size).decode('utf8')

            if self.exit_signal.is_set():
                break

            if not chatMessage:
                break

            if '/quit' in chatMessage[:5].lower():
                self.quit(user)
                break
            elif '/help' in chatMessage[:5].lower():
                self.help(user)
            elif '/join' in chatMessage[:5].lower():
                self.join(user, chatMessage)
            elif '/list' in chatMessage[:5].lower():
                self.list_all_channels(user)
            elif '/time' in chatMessage[:5].lower():
                self.time(user)
            elif '/nick' in chatMessage[:5].lower():
                self.nick(user, chatMessage)
            elif '/userhost' in chatMessage.lower():
                self.userhost(user, chatMessage)
            elif '/part' in chatMessage[:5].lower():
                self.part(user)
            elif '/topic' in chatMessage[:6].lower():
                self.topic(user, chatMessage)
            elif '/whois' in chatMessage[:6].lower():
                self.whois(user, chatMessage)
            elif '/users' in chatMessage[:6].lower():
                self.users_command(user)
            elif '/who' in chatMessage[:4].lower():
                self.who(user, chatMessage)
            elif '/ison' in chatMessage[:5].lower():
                self.ison(user, chatMessage)
            elif '/invite' in chatMessage[:7].lower():
                self.invite(user, chatMessage)
            elif '/restart' in chatMessage[:8].lower():
                self.restart()
            else:
                self.send_message(user, chatMessage + '\n')

        if self.exit_signal.is_set():
            user.socket.sendall('/squit'.encode('utf8'))

        user.socket.close()

    def quit(self, user):
        user.socket.sendall('/quit'.encode('utf8'))
        self.remove_user(user)

    def list_all_channels(self, user):
        if len(self.channels) == 0:
            chatMessage = "\n> No rooms available. Create your own by typing /join [channel_name]\n".encode('utf8')
            user.socket.sendall(chatMessage)
        else:
            chatMessage = '\n\n> Current channels available are: \n'
            for channel in self.channels:
                chatMessage += "    \n" + channel + ": " + str(len(self.channels[channel].users)) + " user(s)"
            chatMessage += "\n"
            user.socket.sendall(chatMessage.encode('utf8'))

    def help(self, user):
        print("channels:")
        print(self.channels)
        print("users_channels_map:")
        print(self.users_channels_map)
        print("users:")
        print(self.users)
        print("client_thread_list:")
        print(self.client_thread_list)

        user.socket.sendall(Server.HELP_MESSAGE)

    def join(self, user, chatMessage):
        isInSameRoom = False

        if len(chatMessage.split()) >= 2:
            channelName = chatMessage.split()[1]

            if user.username in self.users_channels_map:  # Here we are switching to a new channel.
                if self.users_channels_map[user.username] == channelName:
                    user.socket.sendall("\n> You are already in channel: {0}".format(channelName).encode('utf8'))
                    isInSameRoom = True
                else:  # switch to a new channel
                    oldChannelName = self.users_channels_map[user.username]
                    self.channels[oldChannelName].remove_user_from_channel(user) # remove them from the previous channel

            if not isInSameRoom:
                if not channelName in self.channels:
                    newChannel = Channel.Channel(channelName)
                    self.channels[channelName] = newChannel

                self.channels[channelName].users.append(user)
                self.channels[channelName].welcome_user(user.username)
                self.users_channels_map[user.username] = channelName
        else:
            self.help(user)

    def send_message(self, user, chatMessage):
        if user.username in self.users_channels_map:
            self.channels[self.users_channels_map[user.username]].broadcast_message(chatMessage, "{0}{1}:".format(Util.time_text(), user.username))
        else:
            chatMessage = """\n> You are currently not in any channels:

Use /list to see a list of available channels.
Use /join [channel name] to join a channel.\n\n""".encode('utf8')

            user.socket.sendall(chatMessage)

    def remove_user(self, user):
        if user.username in self.users_channels_map:
            self.channels[self.users_channels_map[user.username]].remove_user_from_channel(user)
            del self.users_channels_map[user.username]

        self.users.remove(user)
        print("Client: {0} has left\n".format(user.username))

    def server_shutdown(self):
        print("Shutting down chat server.\n")
        self.serverSocket.close()

    def time(self, user):
        user.socket.sendall(("\n== Time is: " + time.asctime()).encode('utf8'))

    def whois(self, user, chatMessage):
        print("Userhost command is executed")

        splitMessage = chatMessage.split()

        if len(splitMessage) == 2:

            username = splitMessage[1]

            for other_user in self.users:

                print(other_user.username)
                print(username)

                if other_user.username == username:
                    user_info = other_user.username + " " + other_user.nickname + " " + other_user.status + " " + other_user.usertype
                    user.socket.sendall(("\n== User info: " + user_info).encode('utf8'))
                    return

            user.socket.sendall(("\n== No user found").encode('utf8'))
        else:
            user_info = user.username + " " + user.nickname + " " + user.status + " " + user.usertype
            print(user_info)
            user.socket.sendall(("\n== Invalid parameters. Try again following the pattern /whois [<server>] <nickmask>[,<nickmask>[,...]]").encode('utf8'))

    def users_command(self, user):

        for a_user in self.users:
            user_info = a_user.username + " " + a_user.nickname + " " + a_user.status + " " + a_user.usertype
            user.socket.sendall(("\n== User: " + user_info).encode('utf8'))

    def ison(self, user, chatMessage):
        print("Ison command is executed")
        splitMessage = chatMessage.split()
        message = '\n== '

        if len(splitMessage) > 1:

            for username in splitMessage[1:]:
                for a_user in self.users:
                    if a_user.username == username:
                        message += a_user.username + " "

            user.socket.sendall(message.encode('utf8'))

        else:
            user.socket.sendall((
                "\n== Invalid parameters. Try again following the pattern /ison <nicknames>").encode(
                'utf8'))

    def who(self, user, chatMessage):
        print("Who command is executed")
        splitMessage = chatMessage.split()

        if len(splitMessage) == 2:

            username = splitMessage[1]

            for other_user in self.users:

                print(other_user.username)
                print(username)

                if other_user.username == username:
                    user_info = other_user.username + " " + other_user.nickname + " " + other_user.status + " " + other_user.usertype
                    user.socket.sendall(("\n== User info: " + user_info).encode('utf8'))
                    return

            user.socket.sendall(("\n== No user found").encode('utf8'))
        else:
            user_info = user.username + " " + user.nickname + " " + user.status + " " + user.usertype
            print(user_info)
            user.socket.sendall((
                                "\n== Invalid parameters. Try again following the pattern /who <nickname>").encode(
                'utf8'))

    def userhost(self, user, chatMessage):

        print("Userhost command is executed")

        splitMessage = chatMessage.split()

        if len(splitMessage) == 2:

            username = splitMessage[1]

            for other_user in self.users:

                print(other_user.username)
                print(username)

                if other_user.username == username:
                    user_info = other_user.username + " " + other_user.nickname + " " + other_user.status + " " + other_user.usertype
                    user.socket.sendall(("\n== User info: " + user_info).encode('utf8'))
                    return

            user.socket.sendall(("\n== No user found").encode('utf8'))
        else:
            user_info = user.username + " " + user.nickname + " " + user.status + " " + user.usertype
            print(user_info)
            user.socket.sendall(("\n== Invalid parameters. Try again following the pattern /userhost <nickname>{<space><nickname>}").encode('utf8'))

    def invite(self, user, chatMessage):
        print("Invite command is executed")
        splitMessage = chatMessage.split()

        print(splitMessage)
        print(len(splitMessage))

        if len(splitMessage) == 3:
            username = splitMessage[1]
            channel = splitMessage[2]

            for a_user in self.users:

                if a_user.username == username:
                    a_user.socket.sendall(("\n== " + user.username + " invites you to join " + channel).encode('utf8'))
                    user.socket.sendall(("\n== " + a_user.username + " " + channel).encode('utf8'))
                    return
            user.socket.sendall(("\n==No such user: " + username).encode('utf8'))

        else:
            user.socket.sendall(
                ("\n== Invalid parameters. Try again following the pattern /invite <nickname> <channel>").encode(
                    'utf8'))

    def nick(self, user, chatMessage):

        # bug: needs to modify username that are in channels. it is not easy.

        splitMessage = chatMessage.split()
        if len(splitMessage) == 2:
        ### update current box
            print(user.username)
            user.username = chatMessage.split()[1]
            print(user.username)
            user.socket.sendall(("\n== You changed your name to {0}".format(user.username)).encode('utf8'))
        else:
            user.socket.sendall(("\n== Invalid parameters. Try again following the pattern /nick <username>").encode('utf8'))

    def part(self, user):

        print("Part command is executed")
        user.socket.sendall((user.username + " has left the channel.").encode('utf8'))

    def topic(self, user, chatMessage):

        ### check if not in channel

        print("Topic command is executed")

        splitMessage = chatMessage.split()

        if len(splitMessage) > 2:
            channelName = splitMessage[1]
            topicMessage = " ".join(splitMessage[2:])
            self.channels[channelName].topic = topicMessage
            user.socket.sendall(("\n== Topic of channel changed to: " + topicMessage).encode('utf8'))
        elif len(splitMessage) == 2:
            channelName = splitMessage[1]
            channelTopic = self.channels[channelName].topic

            user.socket.sendall(("\n== Topic of channel " + channelName + " is: " + channelTopic).encode('utf8'))
        else:
            user.socket.sendall(("\n== Invalid parameters. Try again following the pattern /topic <channel> [<topic>]").encode('utf8'))

    def restart(self):
        self.serverSocket.shutdown()


def main():
    chatServer = Server()

    print("\nListening on port {0}".format(chatServer.address[1]))
    print("Waiting for connections...\n")

    chatServer.start_listening()
    chatServer.server_shutdown()

if __name__ == "__main__":
    main()
