'''
handled_bug_report.py

Copyright 2009 Andres Riancho

This file is part of w3af, w3af.Trac.net .

w3af is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 2 of the License.

w3af is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with w3af; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

'''
import gtk

from core.controllers.exception_handling.helpers import gettempdir
from core.ui.gui.exception_handling.common_windows import (simple_base_window,
                                                           trac_multi_bug_report)

    

class bug_report_window(simple_base_window, trac_multi_bug_report):
    '''
    The first window that the user sees when the scan finished and there were
    exceptions raised and captured by the new exception handler. 
    
    Please note that in this case we're reporting ONE or MORE exceptions
    and then we simply forget about them. Completely different from what you can
    see in unhandled.py . 
    '''
    
    def __init__(self, w3af_core, title ):
        simple_base_window.__init__(self)
        
        exception_list = w3af_core.exception_handler.get_all_exceptions()
        scan_id = w3af_core.exception_handler.get_scan_id()
        
        trac_multi_bug_report.__init__(self, exception_list, scan_id )
        
        # We got here because of an autogenerated bug, not because of the user
        # going to the Help menu and then clicking on "Report a bug"
        self.autogen = True
        
        # Set generic window settings
        self.set_modal(True)
        self.set_title(title)
        
        self.vbox = gtk.VBox()
        self.vbox.set_border_width(10)
        
        # the label for the title
        self.title_label = gtk.Label()
        self.title_label.set_line_wrap(True)
        label_text = _('<b>The following exceptions were raised and handled</b>')
        self.title_label.set_markup(label_text)
        self.title_label.show()
        
        # A gtk.TextView for the exception
        frame = gtk.Frame('Handled exceptions')
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.set_size_request(200, 280)
        
        # Create the TreeStore to display all exceptions
        self.treestore = gtk.TreeStore(str, str)

        for edata in exception_list:
            where = edata.get_where()
            exception = str(edata.exception)
            tdata = [ where,
                      exception]
            self.treestore.append(None, tdata)

        # create the TreeView using treestore
        self.treeview = gtk.TreeView(self.treestore)

        # First column that holds the icon and the location
        tvcol = gtk.TreeViewColumn('Location')
        
        cell = gtk.CellRendererPixbuf()
        pb = self.treeview.render_icon(gtk.STOCK_DND, gtk.ICON_SIZE_SMALL_TOOLBAR, None)
        cell.set_property('pixbuf', pb)
        tvcol.pack_start(cell, expand=False)
        
        cell = gtk.CellRendererText()
        tvcol.pack_start(cell, expand=False)
        tvcol.add_attribute(cell, "text", 0)
        self.treeview.append_column(tvcol)
        
        # Second column that holds the exception
        tvcol = gtk.TreeViewColumn('Exception')
        cell = gtk.CellRendererText()
        tvcol.pack_start(cell, expand=True)
        tvcol.add_attribute(cell, "text", 1)
        self.treeview.append_column(tvcol)
        
        sw.add(self.treeview)
        frame.add(sw)
        
        # the label for the rest of the message
        self.label = gtk.Label()
        self.label.set_line_wrap(True)
        label_text = _("<i>All these exceptions were stored in '%s' for your later"
                       ' review.</i>\n\nReporting these is recommended and will'
                       ' help us improve w3af. <b>You can contribute</b> to the'
                       ' w3af project and submit these exceptions to our'
                       ' bug tracking system from within this window only using'
                       ' <i>two clicks</i>.\n\n'
                       'w3af will only send the exception traceback and the'
                       ' version information to Trac, no personal or '
                       ' confidential information is collected.')
        self.label.set_markup( label_text % gettempdir() )
        self.label.show()
        
        self.vbox.pack_start(self.title_label, True, True, 10)
        self.vbox.pack_start(frame, True, True)
        self.vbox.pack_start(self.label, True, True, 10)
        
        # the buttons
        self.hbox = gtk.HBox()
        
        self.butt_cancel = gtk.Button(stock=gtk.STOCK_CANCEL)
        self.butt_cancel.connect("clicked", self._handle_cancel)
        self.hbox.pack_start(self.butt_cancel, True, False)

        self.butt_send = gtk.Button(stock=gtk.STOCK_OK)
        self.butt_send.connect("clicked", self.report_bug)
        self.hbox.pack_start(self.butt_send, True, False)
        
        self.vbox.pack_start(self.hbox, True, False, 10)
        
        #self.resize(400,450)
        self.add(self.vbox)
        self.show_all()
        
        # This is a quick fix to get around the problem generated by
        # "set_selectable" that selects the text by default
        self.label.select_region(0, 0)
    
    def report_bug(self, widg):
        # Avoid "double clicking" in the OK button,
        self.butt_send.set_sensitive(False)
        
        # Report the bug
        trac_multi_bug_report.report_bug(self)

    