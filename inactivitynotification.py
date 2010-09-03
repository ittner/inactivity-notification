#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import os
import os.path
import dbus.service
import dbus.glib
import gobject
import time
import datetime

MONITOR_BUS = "br.com.ittner.FileMonitor"
MONITOR_OBJECT = "/br/com/ittner/FileMonitor"
MONITOR_INTERFACE = "br.com.ittner.FileMonitor"


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
        if self.timer:
            gobject.source_remove(self.timer)
        self.timer = gobject.timeout_add_seconds(seconds, self._process)

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
    print("Monitor files for expected updates")
    print("Commands:")
    print(" start")
    print(" stop")
    print(" timer <seconds>")
    print(" addstart <file> <timeout> <short message> [long message [icon]]")
    print(" add <file> <timeout> <short message> [long message [icon]]")
    print(" remove <file> [...]")
    print(" list")


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
            print("Failed to get ownership of the bus. Already running?")
        return

    if not command in [ "stop", "add", "remove", "list", "timer" ]:
        usage()
        return

    obj = find_server()
    if not obj:
        print("Server not found")
        return

    if command == "stop":
        obj.stop_server()
        return

    if command == "timer":
        if len(args) == 0:
            print("How many seconds?")
            return
        try:
            obj.set_timer(int(args[0]))
        except:
            print("Bad number")
        return

    if command == "remove":
        if len(args) == 0:
            print("No file to remove")
            return
        for fname in args:
            fname = os.path.realpath(fname)
            obj.remove_file(fname)
        return

    if command == "list":
        for mf in obj.list_files():
            print(mf[0] + '\t' + str(mf[1]) + '\t' + str(mf[2]) + '\t' + str(mf[3]) + '\t' + str(mf[4]))

    if command == "add":
        if len(args) < 3 or len(args) > 5:
            usage()
            return

        fname = args[0]
        fullname = os.path.realpath(fname)
        if not os.path.exists(fullname):
            print("File not found")
            return
        try:
            timeout = int(args[1])
        except:
            print("Timeout must be a number of seconds. (sei, deveria ser horas...)")
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
    interpret(sys.argv)
