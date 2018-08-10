#!/usr/bin/env python3

# TODO:
    # each pool
        # outstanding since
    # harden with assertions
    # test with real email
    # move to own repo
    # systemd service
    # deploy

from datetime import datetime, timedelta
from getpass import getpass
from json import dump, dumps, load
from os import path
from re import findall
from smtplib import SMTP
from socket import gethostname
from subprocess import PIPE, Popen, STDOUT
from time import sleep
try:
    from private import username, password, server, sender, recipient
except:
    pass


class Zmonitor:
    """
    Checks zpool status periodically and sends an email to
    a specified recipient if the status changes.
    Additionally, the recipient is periodically notified
    until the zpool status is restored.
    """
    def __init__(
                self,
                intervalHours=8, reminderDays=7,
                emailServer=None,
                sender=None, recipient=None,
                filename=None, metaFilename=None
            ):
        """
        intervalHours is the number of hours between each check.

        reminderDays is the number of days between each subsequent notification,
        in the case that any zpool remains degraded.
        """
        for var in (intervalHours, reminderDays):
            assert isinstance(var, (int, float)), 'Must be int or float'
        self.delta = timedelta(hours=intervalHours)
        self.reminder = timedelta(days=reminderDays)
        if emailServer:
            assert isinstance(emailServer, str), 'Must be str or None'
        self.emailServer = 'smtp.gmail.com' if emailServer is None else emailServer
        for var in (filename, metaFilename):
            if var is not None:
                assert isinstance(var, str), 'Must be str or None'
        self.filename = 'zpool_status.json' if filename is None else filename
        self.metaFilename = 'zpool_meta.json'if metaFilename is None else metaFilename
        self.load_index()
        self.load_meta()
        self.index, self.out = self.lastIndex, ''
        self.get_contact_info(sender, recipient)

    def __str__(self):
        return '\n'.join([f'{pool}\t{state}' for pool, state in self.index.items()])

    def __repr__(self):
        return "'\n'.join([f'{pool}\t{state}' for pool, state in self.index.items()])"

    @property
    def healthy(self):
        """Returns True if all zpools in system are online"""
        return all(state == 'ONLINE' for state in self.index.values())

    @property
    def degraded_since(self):
        pass

    @property
    def outstanding(self):
        """
        Returns True if a given number of time has passed since detecting
        a degraded pool.  By default, this is once per week.
        """
        if self.lastNotified is not None:
            return (
                    (datetime.now() - self.lastNotified > self.reminder)
                    and not self.healthy
                )

    @staticmethod
    def subproc(command):
        """
        Opens a subprocess,
        and returns both stdout and stderr as one string.
        """
        proc = Popen(command.split(), stdout=PIPE, stderr=STDOUT)
        return proc.communicate()[0].decode()

    def save_index(self):
        """
        Saves the zpool status index to disk as a json file,
        in case the script stops running
        or the machine is rebooted.
        """
        assert isinstance(self.index, dict), 'Must be dict'
        with open(self.filename, 'w') as status:
            dump(self.index, status, sort_keys=True, indent=4)

    def get_contact_info(self, sender, recipient):
        if sender:
            self.sender = sender
        else:
            self.sender = input('Sender address: ').rstrip()
        if recipient:
            self.recipient = recipient
        else:
            self.recipient = input('Recipient address: ').rstrip()
        self.header = self.sender, self.recipient, gethostname()
        print('Enter sender login information')
        self.__login__ = getpass('username: '), getpass('password: ')

    def load_index(self):
        """Loads the index from disk"""
        if path.exists(self.filename):
            with open(self.filename, 'r') as index:
                self.lastIndex = load(index)
        else:
            self.lastIndex = None
        return self.lastIndex

    def save_meta(self):
        """Saves metadata to disk"""
        now = datetime.now()
        message = {'lastNotified': self.lastNotified.strftime('%H%M%S_%d%m%Y')}
        with open(self.filename, 'w') as metadata:
            dump(message, metadata, sort_keys=True, indent=4)

    def load_meta(self):
        """
        Loads saved metadata to determine the last date and time
        the recipient was notified, if ever.
        """
        if path.exists(self.metaFilename):
            with open(self.metaFilename, 'r') as metadata:
                lastMeta = load(metadata)
            self.lastNotified = lastMeta['lastNotified'].strptime('%H%M%S_%d%m%Y')
        else:
            self.lastNotified = None

    def check_zpools(self):
        """
        Runs the subprocess and return an index
        of each zpool and its status
        """
        self.out = self.subproc('zpool status')
        pools = findall('(?<=pool\:\s).+', self.out)
        states = findall('(?<=state\:\s).+', self.out)
        self.index = {pool: state for pool, state in zip(pools, states)}

    def send_email(self):
        """
        Notifies the recipient of the status
        Includes both a summary and the full subprocess output as a string.
        """
        print('Notifying recipient...')
        message = 'From: {}\nTo: {}\nSubject: Zpool Status on {}\n{}\n\n{}'
        unabridged = f'Unabridged Status:\n\n{self.out}'
        if self.outstanding:
            pass
        print('Logging in...')
        with SMTP(server, timeout=90) as notifier:
            notifier.starttls()
            notifier.login(self.__login__)
            print('Sending message...')
            notifier.sendmail(
                    self.sender, self.recipient,
                    message.format(*self.header, self.__str__, unabridged)
                )
            notifier.quit()
            print('Message sent')

    def notify(self):
        """Manage metadata when attempting an email notification"""
        try:
            self.send_email()
        except:
            print('Failed to notify recipient!')
        else:
            self.lastNotified = datetime.now()
            self.save_meta()
            self.lastIndex = self.index

    def changed(self):
        """Determines whether to trigger a notification"""
        return (
                (self.index != self.lastIndex and self.lastIndex is not None)
                or self.outstanding
            )

    def run(self):
        """
        Check zpool status via a subprocess at a specified interval.
        If the status has changed since the last check, notify the
        recipient.
        """
        print('Started zpool monitor')
        while True:
            self.check_zpools()
            if self.changed():
                if not self.outstanding:
                    print('Zpool status changed!')
                    self.save_index()
                self.notify()
            sleep(self.delta.seconds)


if __name__ == '__main__':
    monitor = Zmonitor()
    monitor.run()
