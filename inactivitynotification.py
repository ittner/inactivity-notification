#!/usr/bin/python
# -*- coding: utf-8 -*-

USAGE = u"""
This program monitor files which are expected to be updated at periodic
intervals and emits desktop notifications when they become outdated.

The following commands are accecpted:

  start
    Starts the server process. The program will not return until finished.
    If there is another server process running for the current user, just
    prints an error and exits.
  
  stop
    Stops any running instance.

  timer <minutes>
    Sets the verification/notification interval to the given number of
    minutes.

  add <file> <timeout> <short message> [<long message> [icon]]
    Adds a file to the verification queue.
  
  remove <file> [...]
    Remove the given file from the verification queue.
    
  list
    List the currently monitored files.


"""

MONITOR_BUS = "br.com.ittner.FileMonitor"
MONITOR_OBJECT = "/br/com/ittner/FileMonitor"
MONITOR_INTERFACE = "br.com.ittner.FileMonitor"


import sys
import os
import os.path
import dbus.service
import dbus.glib
import gobject
import time
import datetime
import locale
import codecs

class MonitoredFile(object):

    def __init__(self, path, timeout, summary, message, icon):
        self.path = path
        self.timeout = timeout
        self.summary = summary
        self.message = message
        self.icon = icon

    def check_update(self):
        try:
            mtime = os.stat(self.path).st_mtime
            tdiff = time.time() - mtime
            if tdiff < self.timeout:
                return False
            summary = self.summary
            message = time.strftime(self.message, time.localtime(mtime))
        except:
            summary = "Failed to verify " + self.path
            message = "There was an error in the verification process"
        sbus = dbus.SessionBus()
        notify_bus = sbus.get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications")
        notify = dbus.Interface(notify_bus, "org.freedesktop.Notifications")
        notify.Notify(MONITOR_BUS, 0, self.icon, summary, message, [], {}, 9000)
        return True

    def to_tuple(self):
        return (self.path, self.timeout, self.summary, self.message, self.icon)



class Monitor(dbus.service.Object):

    def __init__(self, mainloop):
        self.mainloop = mainloop
        self.timer = None
        self.files = [ ]
        sbus = dbus.SessionBus()
        mbus = dbus.service.BusName(MONITOR_BUS, bus=sbus)
        self.set_timer(15*60)
        dbus.service.Object.__init__(self, mbus, MONITOR_OBJECT)

    def try_register(self):
        sbus = dbus.SessionBus()
        res = sbus.request_name(MONITOR_BUS, dbus.bus.NAME_FLAG_DO_NOT_QUEUE)
        return ( res == dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER or \
            res == dbus.bus.REQUEST_NAME_REPLY_ALREADY_OWNER )

    @dbus.service.method(MONITOR_INTERFACE)
    def stop_server(self):
        self.mainloop.quit()

    @dbus.service.method(MONITOR_INTERFACE, in_signature="sisvv")
    def add_file(self, path, timeout, summary, message=None, icon=None):
        self.remove_file(path)
        mf = MonitoredFile(path, timeout, summary, message, icon)
        self.files.append(mf)
        return True

    @dbus.service.method(MONITOR_INTERFACE, in_signature="s", out_signature="b")
    def remove_file(self, path):
        for mf in self.files:
            if mf.path == path:
                self.files.remove(mf)
                return True
        return False

    @dbus.service.method(MONITOR_INTERFACE, out_signature="a(sisvv)")
    def list_files(self):
        return [ mf.to_tuple() for mf in self.files ]

    @dbus.service.method(MONITOR_INTERFACE, in_signature="i")
    def set_timer(self, seconds):
        if seconds < 1: return False    # Error
        if self.timer:
            gobject.source_remove(self.timer)
        self.timer = gobject.timeout_add_seconds(seconds, self._process)
        return True

    def _process(self):
        for f in self.files:
            f.check_update()
        return True



def find_server():
    try:
        sbus = dbus.SessionBus()
        mbus = sbus.get_object(MONITOR_BUS, MONITOR_OBJECT)
        obj = dbus.Interface(mbus, MONITOR_INTERFACE)
        if obj: return obj
    except: pass
    return None


def usage():
    stderr.write(USAGE)


def interpret(args):
    if len(args) < 2:
        usage()
        return

    del args[0]
    command = args[0]
    del args[0]

    if command == "start":
        loop = gobject.MainLoop()
        srv = Monitor(loop)
        if srv.try_register():
            loop.run()
        else:
            stdout.write("Failed to get ownership of the bus. Already running?\n")
        return

    if not command in [ "stop", "add", "remove", "list", "timer" ]:
        usage()
        return

    obj = find_server()
    if not obj:
        stdout.write("Server not found\n")
        return

    if command == "stop":
        obj.stop_server()
        return

    if command == "timer":
        if len(args) == 0:
            stdout.write("How many seconds?\n")
            return
        try:
            obj.set_timer(int(args[0]))
        except:
            stdout.write("Bad number\n")
        return

    if command == "remove":
        if len(args) == 0:
            stdout.write("No file to remove\n")
            return
        for fname in args:
            fname = os.path.realpath(fname)
            obj.remove_file(fname)
        return

    if command == "list":
        for mf in obj.list_files():
            stdout.write(mf[0] + '\t' + str(mf[1]) + '\t' + mf[2] + '\t' + mf[3] + '\t' + mf[4] + "\n")

    if command == "add":
        if len(args) < 3 or len(args) > 5:
            usage()
            return

        fname = args[0]
        fullname = os.path.realpath(fname)
        if not os.path.exists(fullname):
            stdout.write("File not found\n")
            return
        try:
            timeout = int(args[1])
        except:
            stdout.write("Timeout must be a number of seconds. (sei, deveria ser horas...)\n")
            return
        summary = args[2]
        if len(args) > 3:
            message = args[3]
        else:
            message = "File " + fname + " untouched since %x %X"
        if len(args) == 5:
            icon = args[4]
        else:
            icon = ""
        obj.add_file(fullname, timeout, summary, message, icon)




if __name__ == '__main__':
    enc = "utf-8"       # use Unicode or die, baby
    stdout = codecs.getwriter(enc)(sys.stdout)
    stderr = codecs.getwriter(enc)(sys.stderr)
    fixed_argv = [ s.decode(enc) for s in sys.argv ]
    sys.exit(interpret(fixed_argv) or 0)
