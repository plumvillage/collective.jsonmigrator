import time
import string
import httplib
import urllib
import urllib2
import urlparse
import xmlrpclib
import simplejson
from base64 import encodestring
from zope.interface import implements
from zope.interface import classProvides
from zope.component import getUtility
from plone.registry.interfaces import IRegistry
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.jsonmigrator import logger


class BasicAuth(xmlrpclib.Transport):

    def __init__(self, username=None, password=None, verbose=False):
        self.username = username
        self.password = password
        self.verbose = verbose
        self._use_datetime = True

    def request(self, host, handler, request_body, verbose):
        h = httplib.HTTP(host)

        h.putrequest("POST", handler)
        h.putheader("Host", host)
        h.putheader("User-Agent", self.user_agent)
        h.putheader("Content-Type", "text/xml")
        h.putheader("Content-Length", str(len(request_body)))

        if self.username is not None and self.password is not None:
            h.putheader("AUTHORIZATION", "Basic %s" % string.replace(
                    encodestring("%s:%s" % (self.username, self.password)),
                    "\012", ""))
        h.endheaders()

        if request_body:
            h.send(request_body)

        errcode, errmsg, headers = h.getreply()

        if errcode != 200:
            raise xmlrpclib.ProtocolError(
                host + handler,
                errcode, errmsg,
                headers
                )

        return self.parse_response(h.getfile())

class Urllibrpc(object):
    def __init__(self, url, username, password):
        self.url = url
        self.username = username
        self.password = password

    def __getattr__(self, item):
        def callable():
            scheme,netloc,path,params,query,fragment = urlparse.urlparse(self.url)
            if '@' not in netloc:
                netloc = '%s:%s@%s'%(self.username, self.password, netloc)
            path = path + '/' + item
            url = urlparse.urlunparse( (scheme,netloc,path,params,query,fragment) )
            f = urllib.urlopen(url)
            content = f.read()
            if f.getcode() != 200:
                raise Exception(content)
            f.close()
            return content
        return callable
        

class RemoteSource(object):
    """ """

    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.name, self.options = name, options
        self.transmogrifier, self.previous = transmogrifier, previous
        self.context = transmogrifier.context

        self.registry = getUtility(IRegistry)
        self.start_time = time.time()
        self.logger = logger

        #self.remote_url = 'http://192.168.1.55:8080/Plone'
        self.remote_url = options.get('remote-url')
#                self.registry.get('collective.jsonmigrator.remoteurl')
        #self.remote_username ='admin'
        self.remote_username = options.get('remote-username')
#                self.registry.get('collective.jsonmigrator.username')
        #self.remote_password = 'admin'
        self.remote_password = options.get('remote-password')
#                self.registry.get('collective.jsonmigrator.password')

        self.remote_path = self.options.get('remote-path', '/Plone')
        self.remote_crawl_depth = int(self.options.get('remote-crawl-depth', -1))
        self.skip_remote_path = self.options.get('skip-remote-path', '').split()

    def __iter__(self):
        for item in self.previous:
            yield item

        try:
            for item in self.get_items(self.remote_path):
                if item:
                    yield item
        except Exception, e:
            import ipdb; ipdb.set_trace()

    def get_items(self, path, depth=0):
        if self.remote_crawl_depth == -1 or depth <= self.remote_crawl_depth:
            self.logger.info(':: Crawling %s' % path)
            remote = self.get_remote_item(path)
            item = None

            try:
                item = remote.get_item()
            except xmlrpclib.ProtocolError, e:
                self.logger.error(
                        'XML-RPC protocol error:\n'
                        '    URL: %s\n'
                        '    HTTP headers: %s\n'
                        '    %s: %s' %
                            (e.url, e.headers, e.errcode, e.errmsg))
                raise Exception('error1')
            except Exception, e:
                import ipdb; ipdb.set_trace()

            if item.startswith('ERROR'):
                self.logger.error('%s :: EXPORT %s' % (path, item))
                # Item could be portal object that has children but we can't import
                # Keep going and assume we have container already to put this content in
                #raise Exception('error2')
            elif item is not None:
                try:
                    item = simplejson.loads(item)
                except:
                    import ipdb; ipdb.set_trace()
                yield item

            try:
                subitems = remote.get_children()
            except xmlrpclib.ProtocolError, e:
                self.logger.error(
                        'XML-RPC protocol error:\n'
                        '    URL: %s\n'
                        '    HTTP headers: %s\n'
                        '    %s: %s' %
                            (e.url, e.headers, e.errcode, e.errmsg))
                raise Exception('error3')

            if subitems.startswith('ERROR'):
                self.logger.error('%s :: \n%s' % (path, item))
                raise Exception('error4')

            for subitem_id in simplejson.loads(subitems):
                subitem_path = path + '/' + subitem_id

                if subitem_path[len(self.remote_path):] in self.skip_remote_path:
                    logger.info(':: Skipping -> ' + subitem_path)
                    continue

                for subitem in self.get_items(subitem_path, depth+1):
                    yield subitem

    def get_remote_item(self, path):
        remote_url = self.remote_url
        if not remote_url.endswith('/'):
            remote_url += '/'
        if path.startswith('/'):
            path = path[1:]
        url = urllib2.urlparse.urljoin(remote_url, urllib.quote(path))
        return xmlrpclib.Server(url,
                BasicAuth(self.remote_username, self.remote_password),
                )

    def get_remote_item(self, path):
        remote_url = self.remote_url
        if not remote_url.endswith('/'):
            remote_url += '/'
        if path.startswith('/'):
            path = path[1:]
        url = urllib2.urlparse.urljoin(remote_url, urllib.quote(path))
        return Urllibrpc(url, self.remote_username, self.remote_password)