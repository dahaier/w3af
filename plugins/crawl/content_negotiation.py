'''
content_negotiation.py

Copyright 2006 Andres Riancho

This file is part of w3af, w3af.sourceforge.net .

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
import os
import re
import Queue

from itertools import izip, repeat

import core.controllers.outputManager as om
import core.data.kb.knowledgeBase as kb
import core.data.kb.info as info

from core.data.options.option import option
from core.data.options.optionList import optionList
from core.controllers.basePlugin.baseCrawlPlugin import baseCrawlPlugin
from core.data.bloomfilter.bloomfilter import scalable_bloomfilter


class content_negotiation(baseCrawlPlugin):
    '''
    Use content negotiation to find new resources.
    @author: Andres Riancho (andres.riancho@gmail.com)
    '''

    def __init__(self):
        baseCrawlPlugin.__init__(self)
        
        # User configured parameters
        self._wordlist = os.path.join('plugins', 'crawl', 'content_negotiation',
                                      'common_filenames.db')
        
        # Internal variables
        self._already_tested_dir = scalable_bloomfilter()
        self._already_tested_resource = scalable_bloomfilter()
        self._content_negotiation_enabled = None
        self._to_bruteforce = Queue.Queue()
        # I want to try 3 times to see if the remote host is vulnerable
        # detection is not thaaat accurate!
        self._tries_left = 3

    def crawl(self, fuzzable_request ):
        '''
        1- Check if HTTP server is vulnerable
        2- Exploit using fuzzable_request
        3- Perform bruteforce for each new directory
        
        @parameter fuzzable_request: A fuzzable_request instance that contains 
                                                    (among other things) the URL to test.
        '''
        if self._content_negotiation_enabled is not None \
        and self._content_negotiation_enabled == False:
            return []
            
        else:
            con_neg_result = self._verify_content_neg_enabled( fuzzable_request )
            
            if con_neg_result is None:
                # I can't say if it's vulnerable or not (yet), save the current
                # directory to be included in the bruteforcing process, and return.
                self._to_bruteforce.put(fuzzable_request.getURL())
                return []
            
            elif con_neg_result == False:
                # Not vulnerable, nothing else to do.
                return []
                
            elif con_neg_result == True:
                # Happy, happy, joy!
                # Now we can test if we find new resources!
                new_resources = self._find_new_resources( fuzzable_request )
                
                # and we can also perform a bruteforce:
                self._to_bruteforce.put(fuzzable_request.getURL())
                bruteforce_result = self._bruteforce()
                
                result = []
                result.extend( new_resources )
                result.extend( bruteforce_result )
                
                return result
    
    def _find_new_resources(self, fuzzable_request):
        '''
        Based on a request like http://host.tld/backup.php , this method will find
        files like backup.zip , backup.old, etc. Using the content negotiation
        technique.
        
        @return: A list of new fuzzable requests.
        '''
        result = []
        
        # Get the file name
        filename = fuzzable_request.getURL().getFileName()
        if filename == '':
            return []
        else:
            # The thing here is that I've found that if these files exist in
            # the directory:
            # - backup.asp.old
            # - backup.asp
            #
            # And I request "/backup" , then both are returned. So I'll request
            #  the "leftmost" filename.
            filename = filename.split('.')[0]
            
            # Now I simply perform the request:
            alternate_resource = fuzzable_request.getURL().urlJoin(filename)
            original_headers = fuzzable_request.getHeaders()
            
            if alternate_resource not in self._already_tested_resource:
                self._already_tested_resource.add( alternate_resource )

                _, alternates = self._request_and_get_alternates(alternate_resource,
                                                              original_headers)
           
                # And create the new fuzzable requests
                result = self._create_new_fuzzable_requests( fuzzable_request.getURL(),
                                                             alternates )
        
        return result
    
    def _bruteforce(self):
        '''
        Use some common words to bruteforce file names and find new resources.
        This process is done only once for every new directory.
        
        @return: A list of new fuzzable requests.
        '''
        result = []
        
        wl_url_generator = self._wordlist_url_generator()
        args_generator = izip(wl_url_generator, repeat({}))
        # Send the requests using threads:
        for base_url, alternates in self._tm.threadpool.map_multi_args(
                                                    self._request_and_get_alternates,
                                                    args_generator,
                                                    chunksize=10):
            result = self._create_new_fuzzable_requests( base_url,  alternates )

        return result
    
    def _wordlist_url_generator(self):
        '''
        Generator that returns alternate URLs to test by combining the following
        sources of information:
            - URLs in self._bruteforce
            - Words in the bruteforce wordlist file
        '''
        while True:
            try:
                bf_url = self._to_bruteforce.get_nowait()
            except Queue.Empty:
                break
            else:
                directories = bf_url.getDirectories()
                
                for directory_url in directories:
                    if directory_url not in self._already_tested_dir:
                        self._already_tested_dir.add( directory_url )
            
                        for word in file(self._wordlist):
                            word = word.strip()
                            yield directory_url.urlJoin( word )
    
    def _request_and_get_alternates(self, alternate_resource, headers):
        '''
        Performs a request to an alternate resource, using the fake accept 
        trick in order to retrieve the list of alternates, which is then
        returned.
        
        @return: A tuple with:
                    - alternate_resource parameter (unmodified)
                    - a list of strings containing the alternates.
        '''
        headers['Accept'] = 'w3af/bar'
        response = self._uri_opener.GET( alternate_resource, headers = headers )
        
        # And I parse the result
        if 'alternates' in response.getLowerCaseHeaders():
            alternates = response.getLowerCaseHeaders()['alternates']
            
            # An alternates header looks like this:
            # alternates: {"backup.php.bak" 1 {type application/x-trash} {length 0}}, 
            #                   {"backup.php.old" 1 {type application/x-trash} {length 0}},
            #                   {"backup.tgz" 1 {type application/x-gzip} {length 0}},
            #                   {"backup.zip" 1 {type application/zip} {length 0}}
            #
            # All in the same line.
            return alternate_resource, re.findall( '"(.*?)"', alternates )
        
        else:
            # something failed
            return alternate_resource, []

    def _create_new_fuzzable_requests(self, base_url, alternates):
        '''
        With a list of alternate files, I create new fuzzable requests
        
        @parameter base_url: http://host.tld/some/dir/
        @parameter alternates: ['backup.old', 'backup.asp']
        
        @return: A list of fuzzable requests.
        '''
        result = []
        for alternate in alternates:
            # Get the new resource
            full_url = base_url.urlJoin(alternate)
            response = self._uri_opener.GET( full_url )
                
            result.extend( self._create_fuzzable_requests( response ) )
            
        return result

    def _verify_content_neg_enabled(self, fuzzable_request):
        '''
        Checks if the remote website is vulnerable or not. Saves the result in
        self._content_negotiation_enabled , because we want to perform this test
        only once.
        
        @return: True if vulnerable.
        '''
        if self._content_negotiation_enabled is not None:
            # The test was already performed, we return the old response
            return self._content_negotiation_enabled
            
        else:
            # We perform the test, for this we need a URL that has a filename, URL's
            # that don't have a filename can't be used for this.
            filename = fuzzable_request.getURL().getFileName()
            if filename == '':
                return None
        
            filename = filename.split('.')[0]
            
            # Now I simply perform the request:
            alternate_resource = fuzzable_request.getURL().urlJoin(filename)
            headers = fuzzable_request.getHeaders()
            headers['Accept'] = 'w3af/bar'
            response = self._uri_opener.GET( alternate_resource, headers = headers )
            
            if 'alternates' in response.getLowerCaseHeaders():
                # Even if there is only one file, with an unique mime type, 
                # the content negotiation will return an alternates header.
                # So this is pretty safe.
                
                # Save the result internally
                self._content_negotiation_enabled = True
                
                # Save the result as an info in the KB, for the user to see it:
                i = info.info()
                i.setPluginName(self.getName())
                i.setName('HTTP Content Negotiation enabled')
                i.setURL( response.getURL() )
                i.setMethod( 'GET' )
                desc = 'HTTP Content negotiation is enabled in the remote web server. This'
                desc += ' could be used to bruteforce file names and find new resources.'
                i.setDesc( desc )
                i.setId( response.id )
                kb.kb.append( self, 'content_negotiation', i )
                om.out.information( i.getDesc() )
            else:
                om.out.information('The remote Web server has Content Negotiation disabled.')
                
                # I want to perform this test a couple of times... so I only return False
                # if that "couple of times" is empty
                self._tries_left -= 1
                if self._tries_left == 0:
                    # Save the FALSE result internally
                    self._content_negotiation_enabled = False
                else:
                    # None tells the plugin to keep trying with the next URL
                    return None
            
            return self._content_negotiation_enabled
    
    def getOptions( self ):
        '''
        @return: A list of option objects for this plugin.
        '''
        d1 = 'Wordlist to use in the file name bruteforcing process.'
        o1 = option('wordlist', self._wordlist , d1, 'string')
        
        ol = optionList()
        ol.add(o1)
        return ol

    def setOptions( self, optionsMap ):
        '''
        This method sets all the options that are configured using the user interface 
        generated by the framework using the result of getOptions().
        
        @parameter optionsMap: A dictionary with the options for the plugin.
        @return: No value is returned.
        ''' 
        wordlist = optionsMap['wordlist'].getValue()
        if os.path.exists( wordlist ):
            self._wordlist = wordlist

    def getPluginDeps( self ):
        '''
        @return: A list with the names of the plugins that should be run before the
        current one.
        '''
        return ['crawl.web_spider']
        
    def getLongDesc( self ):
        '''
        @return: A DETAILED description of the plugin functions and features.
        '''
        return '''
        This plugin uses HTTP content negotiation to find new resources.
        
        The plugin has three distinctive phases:

            - Identify if the web server has content negotiation enabled.
            
            - For every resource found by any other plugin, perform a request
            to find new related resources. For example, if another plugin finds
            "index.php", this plugin will perform a request for "/index" with
            customized headers that will return a list of all files that have
            "index" as the file name.
            
            - Perform a brute force attack in order to find new resources.
        
        One configurable parameter exists:
            - wordlist: The wordlist to be used in the bruteforce process.
        
        As far as I can tell, the first reference to this technique was written
        by Stefano Di Paola in his blog (http://www.wisec.it/sectou.php?id=4698ebdc59d15).
        '''