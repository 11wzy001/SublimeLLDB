# -*- mode: python; coding: utf-8 -*-

import sublime
import sublime_plugin

import os
import sys
import atexit
import datetime
import threading

from root_objects import lldb_instance, set_lldb_instance,      \
                         lldb_out_view, set_lldb_out_view,      \
                         lldb_view_write, lldb_view_send,       \
                         lldb_input_fh,  set_lldb_input_fh,     \
                         lldb_output_fh, set_lldb_output_fh,    \
                         lldb_error_fh,  set_lldb_error_fh,     \
                         thread_created

from monitors import launch_i_o_monitor, launch_event_monitor,  \
                     launch_markers_monitor, lldb_file_markers_queue

import lldb

# import this specific name without the prefix
from lldb_wrappers import LldbWrapper
import lldb_wrappers


# import traceback
def debug_thr():
    threading.current_thread()
    1 + 1
    # print ('thread id: ' + threading.current_thread().name)
    # traceback.print_stack()


def debug(str):
    print str


def debugif(b, str):
    if b:
        debug(str)


def initialize_plugin():
    thread_created('<' + threading.current_thread().name + '>')
    debug('Loading LLDB Sublime Text 2 plugin')
    debug('python version: %s' % (sys.version_info,))
    debug('cwd: %s' % os.getcwd())


def debug_prologue(lldb):
    """
    Prologue for the debugging session during the development of the plugin.
    Loads a simple program in the debugger and sets a breakpoint in main()
    """
    debug('lldb prologue')
    # lldb_view_write('(lldb) log enable lldb events\n')
    # lldb_instance().interpret_command('log enable lldb events')
    lldb_view_write('(lldb) target create ~/dev/softek/lldb-plugin/tests\n')
    lldb_instance().interpret_command('target create ~/dev/softek/lldb-plugin/tests')
    lldb_view_write('(lldb) b main\n')
    lldb_instance().interpret_command('b main')
    debug('ended lldb prologue')


def lldb_greeting():
    return datetime.date.today().__str__() + \
           '\nWelcome to the LLDB plugin for Sublime Text 2\n'


lldb_view_name = 'lldb i/o'
lldb_prog_view_name = 'program i/o'
lldb_prompt = '(lldb) '

# lldb_instance = None
# lldb_out_view = None

# To hold on to the pipes. Otherwise GC takes them
# pipe_in = None
# pipe_out = None
# pipe_err = None

broadcaster = None

lldb_prog_view = None
lldb_prog_input = None
lldb_prog_output = None
lldb_prog_error = None
window_ref = None  # For the 'on_done' panel helper
lldb_window_layout = {
                        "cols": [0.0, 1.0],  # start, end
                        "rows": [0.0, 0.75, 1.0],  # start1, start2, end
                        "cells": [[0, 0, 1, 1], [0, 1, 1, 2]]
                     }
basic_layout = {  # 1 group
                    "cols": [0.0, 1.0],
                    "rows": [0.0, 1.0],
                    "cells": [[0, 0, 1, 1]]
               }
# backup_layout = None


def good_lldb_layout(window=window_ref):
    # if the user already has two groups, it's a good layout
    return window.num_groups() == 2


def set_lldb_window_layout(window=window_ref):
    if lldb_out_view() != None and window.num_groups() != 2:
        window.run_command('set_layout', lldb_window_layout)


def set_regular_window_layout(window=window_ref):
    window.run_command("set_layout", basic_layout)


def get_lldb_output_view(window, name):
    # Search for the lldb_view view first.
    f = None
    for v in window.views():
        if v.name() == name:
            f = v
            break

    if f is None:
        f = window.new_file()
        f.set_name(name)

    f.set_scratch(True)
    f.set_read_only(True)
    # f.set_syntax_file('…')  # lldb output syntax
    return f


def lldb_toggle_output_view(window, show=False, hide=False):
    """ Toggles the lldb output view visibility.

            if show=True: force showing the view;
            if hide=True: force hiding the view;
            Otherwise: Toggle view visibility.
    """
    # global lldb_out_view_name
    # TODO: Set the input_panel syntax to 'lldb command'

    # Just show the window.
    v = lldb_out_view()
    if v:
        if show:
            set_lldb_window_layout(window=window)
            window.set_view_index(v, 1, 0)
        elif hide:
            set_regular_window_layout(window=window)
        elif not good_lldb_layout(window=window):
            set_lldb_window_layout(window=window)
            window.set_view_index(v, 1, 0)
        else:
            set_regular_window_layout(window=window)


def clear_lldb_out_view():
    v = lldb_out_view()
    debug('clearing view: ' + repr(v))
    v.set_read_only(False)
    edit = v.begin_edit('lldb-view-clear')
    v.erase(edit, sublime.Region(0, v.size()))
    v.end_edit(edit)
    v.set_read_only(True)
    v.show(v.size())


def lldb_in_panel_on_done(cmd):
    debug_thr()

    # global prompt
    if cmd is None:
        cmd = ''

    lldb_view_write(lldb_prompt + cmd + '\n')

    r = broadcaster.send_command(cmd)
    # err_str = result.error()
    # out_str = result.output()

    # lldb_view_write(out_str)

    # if len(err_str) != 0:
    #     err_str.replace('\n', '\nerr> ')
    #     err_str = 'err> ' + err_str
    #     lldb_view_write(err_str)

    # We don't have a window, so let's re-use the one active on lldb launch
    lldb_toggle_output_view(window_ref, show=True)

    v = lldb_out_view()
    v.show_at_center(v.size() + 1)

    # if r.is_quit():
    #     cleanup(window_ref)
    # else:
    #     update_markers(window_ref, after=lambda:
    #         window_ref.show_input_panel('lldb', '',
    #                                     lldb_in_panel_on_done, None, None))
    window_ref.show_input_panel('lldb', '',
                                lldb_in_panel_on_done, None, None)


def update_markers(window, after=None):
    lldb_file_markers_queue.put({'marks': 'all', 'window': window, 'after': after})


@atexit.register
def atexit_function():
    debug('running atexit_function')
    cleanup(window_ref)


def unload_handler():
    debug('unloading lldb plugin')
    cleanup(window_ref)


def cleanup(window, full=True):
    debug('cleaning up the lldb plugin')

    update_markers(window)  # markers will be removed

    # kill_monitors()
    if lldb_instance() is not None:
        lldb_instance().destroy()
    set_lldb_instance(None)

    # close the pipes
    # if broadcaster is not None:
    #     broadcaster.end()
    # broadcaster = None

    # lldb_wrappers.terminate()


def initialize_lldb():
    lldb_wrappers.initialize()
    lldb = LldbWrapper()

    return lldb


def start_debugging():
    cleanup(window_ref)

    # Really start the debugger
    set_lldb_instance(initialize_lldb())
    lldb_ = lldb_instance()
    debug('setting file handles')
    lldb_.SetInputFileHandle(sys.__stdin__, False)
    lldb_.SetErrorFileHandle(sys.__stderr__, False)
    lldb_.SetOutputFileHandle(sys.__stdout__, False)

    debug('setting up broadcaster')
    global broadcaster
    broadcaster = lldb_wrappers.SublimeBroadcaster(lldb_)
    broadcaster.set_output_fun(lldb_view_send)
    broadcaster.start()

    debug('setting up event monitor')
    launch_event_monitor(broadcaster)

    # launch_i_o_monitor(broadcaster)

    # We may also need to change the width upon window resize
    # debugger.SetTerminalWidth()

    # Setup the input, output, and error file descriptors
    # for the debugger
    # global pipe_in, pipe_out, pipe_err

    # pipe_in, lldb_debugger_pipe_in = os.pipe()
    # lldb_debugger_pipe_out, pipe_out = os.pipe()
    # lldb_debugger_pipe_err, pipe_err = os.pipe()
    # debug('in: %d, %d' % (pipe_in, lldb_debugger_pipe_in))
    # debug('out: %d, %d' % (lldb_debugger_pipe_out, pipe_out))
    # debug('err: %d, %d' % (lldb_debugger_pipe_err, pipe_err))

    # pipe_in = os.fdopen(pipe_in, 'r', 0)
    # set_lldb_input_fh(os.fdopen(lldb_debugger_pipe_in, 'w', 0))
    # set_lldb_output_fh(os.fdopen(lldb_debugger_pipe_out, 'r', 0))
    # pipe_out = os.fdopen(pipe_out, 'w', 0)
    # set_lldb_error_fh(os.fdopen(lldb_debugger_pipe_err, 'r', 0))
    # pipe_err = os.fdopen(pipe_err, 'w', 0)

    # debug('in: %s, %s' % (str(pipe_in), str(lldb_debugger_pipe_in)))
    # debug('out: %s, %s' % (str(lldb_debugger_pipe_out), str(pipe_out)))
    # debug('err: %s, %s' % (str(lldb_debugger_pipe_err), str(pipe_err)))

    # lldb_instance().SetInputFileHandle(pipe_in, True)
    # lldb_instance().SetOutputFileHandle(pipe_out, True)
    # lldb_instance().SetErrorFileHandle(pipe_err, True)

    # launch_i_o_monitor()
    # launch_markers_monitor()



class WindowCommand(sublime_plugin.WindowCommand):
    def setup(self):
        debug_thr()

        # global lldb_out_view
        if lldb_out_view() is None:
            set_lldb_out_view(get_lldb_output_view(self.window, lldb_view_name))  # for lldb output


class LldbCommand(WindowCommand):
    def run(self):
        self.setup()

        global lldb_view_name
        global window_ref

        if lldb_instance() is None:
            # if should_clear_lldb_view:
            clear_lldb_out_view()

            debug('Creating an SBDebugger instance.')
            window_ref = self.window

            start_debugging()

            g = lldb_greeting()
            if lldb_out_view().size() > 0:
                g = '\n\n' + lldb_greeting()
            lldb_view_write(g)
            lldb_view_write('cwd: ' + os.getcwd() + '\n')

            if lldb_out_view() is None:
                debug('uh oh, starting lldb and the i/o view is not ready!')
            self.window.set_view_index(lldb_out_view(), 1, 0)

            debug_prologue(lldb_instance())

        # last args: on_done, on_change, on_cancel.
        # On change we could try to complete the input using a quick_panel.
        self.window.show_input_panel('lldb', '',
                                     lldb_in_panel_on_done, None, None)


class LldbToggleOutputView(WindowCommand):
    def run(self):
        self.setup()

        debug('layout: ' + str(good_lldb_layout(window=self.window)))
        if good_lldb_layout(window=self.window) and basic_layout != None:
            # restore backup_layout (groups and views)
            lldb_toggle_output_view(self.window, hide=True)
        else:
            lldb_toggle_output_view(self.window, show=True)


class LldbClearOutputView(WindowCommand):
    def run(self):
        self.setup()
        debug('clearing lldb view')

        clear_lldb_out_view()

# class LldbNext(sublime_plugin.WindowCommand):
#     def run(self):
#         debugger.

initialize_plugin()
