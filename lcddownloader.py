#!/usr/bin/env python3
import urllib
import json
import os
import re
import sys
import time
import http.client
import logging
from logging import config
import argparse
from bs4 import BeautifulSoup
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.parse import urlparse
from datetime import datetime
import requests
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# default parameter
dry_run = False
oformat = 'mp3'
quality = 1
overwrite_lock = False
start_position = 1
original_list_name = ""
request_timeout = 30

fake_headers = { 'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36'
                }
custom_headers = {}

cdn_formats = ['mp3','mp4','acc','flv','wma','ogg','mkv','avi','rmvb','mpg','mpeg','vob','aif','AIFC','AIF'
        'wav','ape']

"""
LOADERCDN USAGE EXAMPLE
continue_download is not supported!

{
  "id": "6QJsqtl9V",
  "hostname": "site-which-embeds-vimeo-videos.com",
  "link": "https://vimeo.com/165547092",
  "title": "Character: Tuoni: Point",
  "uploader": "Gemma Hanley",
  "track": "Tunoi: Point",
  "resolution": "1280x720",
  "size": "6.4 MB",
  "fps": 30,
  "originalFormat": "mp4",
  "wantedFormat": "mp4",
  "originalType": "video",
  "wantedType": "video",
  "url": "http://dashboard/download?id=6QJs04i92",
  "thumbnail": "http://dashboard/thumbnail?id=6QJs04i92",
  "directThumbnail": "http://dashboard/thumbnail?id=6QJs04i92&direct=true",
  "subtitles": [
    {
      "language": "English",
      "exts": [
        {
          "ext": "srt",
          "url": "http://dashboard/subtitle?id=6QJs04i92&key=English&index=0"
        }
      ]
    }
  ],
  "formats": [
    {
      "format": "mp4",
      "url": "http://dashboard/download?id=6QJs04i92&type=mp4",
      "filename": "My file.mp4"
    },
    {
      "format": "mp3",
      "url": "http://dashboard/download?id=6QJs04i92&type=mp3",
      "filename": "My file.mp3"
    }
  ],
  "qualities": [
    {
      "url": "http://dashboard/download?id=6QJs04i92&quality=1",
      "note": "Ogg Vorbis",
      "format": "ogg",
      "size": "4.4 MB",
      "vcodec": "none"
    },
    {
      "url": "http://dashboard/download?id=6QJs04i92&quality=2",
      "note": "MP3 V0",
      "format": "mp3",
      "size": "5.8 MB",
      "fps": 30,
      "vcodec": "none"
    },
    {
      "url": "http://dashboard/download?id=6QJs04i92&quality=3",
      "note": "1080p",
      "format": "mp4", "vcodec": "h264", "acodec": "aac",
      "size": ""
    },
    {
      "url": "http://dashboard/download?id=6QJs04i92&quality=4",
      "note": "540x311",
      "format": "flv"
    }
  ]
}
"""

def setup_logger():
    if os.path.isfile("logging.json"):
        with open("logging.json", "r", encoding="utf-8") as fd:
            config = json.load(fd)
            log_dir = os.getcwd() + os.path.sep + "log"
            if not os.path.isdir(log_dir):
                os.makedirs(log_dir)
            config['handlers']['file_handler']['filename'] = (log_dir + os.path.sep + "debug-"
                                + os.path.basename(__file__).split('.')[0]) + ".log"
            config['handlers']['warn_handler']['filename'] = (log_dir + os.path.sep + "warn-"
                                + os.path.basename(__file__).split('.')[0]) + ".log"
            logging.config.dictConfig(config)
    else:
        logging.basicConfig(filename="log-basic.txt",
                level=logging.DEBUG,
                format="%(message)s",
                filemode="w")

class loaderCDN():
    stream_types = ['mp4','flv','avi','mp3','wav','ogg','flac']
    api_url = "https://loadercdn.io/api/v1/create"
    api_key = "" # please apply for your own free copy

    def set_key(self,api_key):
        global logger
        if api_key:
            self.api_key = api_key
        else:
            logger.info("Empty api_key. Exit.")
            sys.exit()

    def api_req(self, url, oformat="", direct=False, seek="", duration="", headers=None):
        """
        Use loaderCDN api to parse video url and get direct links
        Documentation: https://loadercdn.docs.apiary.io/
        Return value: dict(response_header,response_content,response_url)
        """
        global logger
        global fake_headers

        if headers is None:
            headers = fake_headers

        #queries = {'format':oformat, 'direct':'true' if direct else '','seek':seek,'duration':duration}
        #url = url + '?' + urlencode(queries) # update on 2018-4, the url entry does not require queries anymore
        values = """
                  {{
                    "key": {api_key},
                    "link": {query_url}
                  }}
                """.format(api_key='"' + self.api_key + '"', query_url='"' + url + '"')

        try:
            request = Request(self.api_url, data=bytes(values,encoding='utf-8'), headers=headers)
            response = urlopen(request)
        except urllib.error.URLError as e:
            logger.exception(e)
            sys.exit(1)

        status_code = response.getcode()
        if status_code == 201:
            response_header = response.getheaders()
            response_content = response.read().decode("utf-8")
            response_url = response.geturl()
            return {'response_header':response_header,'response_content':response_content, 'response_url':response_url}
        else:
            logger.warn(url)
            logger.warn("Server Error: %s", 200)
            message = json.loads(response.read().decode("utf-8"))['message']
            logger.warn("Server message: " + message + os.linesep)
            return None
            #logger.warn("Requests Error: %s", 400)
            #logger.warn("Parameter missing / wrong data type")
            #logger.warn("Requests Error: %s", 401)
            #logger.warn("Invalid API key")

    def parse_response_content(self,response_matrix):
        """
        response_matrix: dict(response_header,response_content,response_url)
        """
        global logger
        # check
        if not isinstance(response_matrix,dict):
            logger.info("parse_response_content error: input not dict")
            sys.exit(1)

        headers = dict(response_matrix['response_header']) # input: list
        content = json.loads(response_matrix['response_content']) # input: string
        requested_url = response_matrix['response_url'] # input: string

        return {'headers':headers, 'content':content, 'url':requested_url}

class ProgressBar(object):
    global logger
    def __init__(self, title, count=0.0, run_status=None, fin_status=None, total=100.0,    unit='', sep='/', chunk_size=1.0):
        super(ProgressBar, self).__init__()
        self.info = "[%s] %s %.2f %s %s %.2f %s"
        self.title = title
        self.total = total
        self.count = count
        self.chunk_size = chunk_size
        self.status = run_status or ""
        self.fin_status = fin_status or " " * len(self.status)
        self.unit = unit
        self.seq = sep

    def __get_info(self):
        # 【名称】状态 进度 单位 分割线 总数 单位
        _info = self.info % (self.title, self.status, self.count/self.chunk_size, self.unit, self.seq, self.total/self.chunk_size, self.unit)
        return _info

    def refresh(self, count=1, status=None):
        self.count += count
        # if status is not None:
        self.status = status or self.status
        end_str = "\r"
        if self.count >= self.total:
            end_str = '\n'
            self.status = status or self.fin_status
        logger.info(self.__get_info(), end_str)

def load_headers(headerfile):
    """
    load header options from headers.txt
    format: key: value \n key: value \n " and ' are allowed
    """
    global custom_headers
    global logger

    try:
        f = open(headerfile,'r')
    except Exception as e:
        logger.exception(e)
        logger.exception("headers.txt open failed. Revert to default fake-headers")

    _headers = {}
    text = f.readlines()
    for line in text:
        if line.strip():
            key, value = line.split(':')
            key = re.sub(r'^\"|^\'|\"$|\'$', '', key.strip())
            value = re.sub(r'^\"|^\'|\"$|\'$|,$|(\'|\"),$','',value.strip())
            _headers[key] = value

    must = False
    for key, value in _headers.items():
        if key == 'Content-Type' and value == 'application/json':
            must = True

    if must:
        print("Custom headers.txt loaded")
        custom_headers = _headers
    else:
        logger.warn("Headers must contain entry: Content-Type: application/json\nCustom headers.txt not loaded")

    return

def bilibili_namer(bili_url):
    """
    Extract title, subtitle from bilibili.com video
    """

    global request_timeout
    global logger

    title = ""
    sub_title = ""

    if "www.bilibili.com/video/av" in bili_url:
        start_time = time.time()
        while True:
            try:
                r = requests.get(bili_url)
                break
            except Exception as e:
                if time.time() - start_time > request_timeout:
                    logger.warn("bilibili_namer timeout: unable to connect after %s s",request_timeout)
                    return [title, sub_title]
                else:
                    logger.exception(e)
                    time.sleep(1)

        soup = BeautifulSoup(r.text,"lxml")
        scriptData = soup.findAll('script')
        scriptINITIALSTATE = ''

        for _script in scriptData:
            if 'window.__INITIAL_STATE__=' in _script.text:
                scriptINITIALSTATE = _script.text

        if not scriptINITIALSTATE:
            logger.warn('window.__INITIAL_STATE__= not exist')
            return [title, sub_title]

        videoData = re.search(r'window.__INITIAL_STATE__=(.*)$', scriptINITIALSTATE).group(1).replace(';(function(){var s;(s=document.currentScript||document.scripts[document.scripts.length-1]).parentNode.removeChild(s);}());', '')
        jsonData = json.loads(videoData)

        aid = jsonData['aid']
        videoCount = jsonData['videoData']['videos']
        title = jsonData['videoData']['title']
        desc = jsonData['videoData']['desc']
        pages = jsonData['videoData']['pages']


        if '?p=' in bili_url:
            page = int(re.search(r'\?p=(.*)$', bili_url).group(1))
            for each_page in pages:
                if each_page['page'] == page:
                    sub_title = each_page['part']

        return [title,sub_title]
    else:
        logger.warn("Not a valid bilibili video link")
        return [title,sub_title]

def download_main(myloader, URLs=None, url_only=False, oformat=oformat,quality=quality):
    global custom_headers
    global fake_headers
    global cdn_formats
    global dry_run
    global overwrite_lock
    global logger

    _headers = custom_headers if custom_headers else fake_headers

    try:
        if URLs is not None:
            print("================================================================================================================")
            logger.info("Total %d urls", len(URLs))
            logger.info("共%d条视频" + os.linesep,len(URLs))
            count = 0
            save_dir = os.getcwd() + os.path.sep + 'downloaded'

            # 检查已下载文件
            # saved_videos = [x[0].split(os.path.sep)[-1] for x in os.walk(save_dir) if os.path.isdir(x[0])]

            if not os.path.isdir(save_dir):
                os.makedirs(save_dir)

            for uri in URLs:
                # 通过普通requests获得文件名，节约loaderCDN api时间和次数
                title=""
                subtitle = ""
                ext = ""

                if len(uri.split('/')[-1].split('.')) > 1:
                    # direct file link.
                    title,ext = uri.split('/')[-1].split('.')
                elif "bilibili" in uri: # needs fix
                    # bilibili.com
                    title, subtitle = bilibili_namer(uri)

                if title:
                    tmp_file = save_dir + os.path.sep + title + os.path.sep + title + '.' + oformat
                    if os.path.isfile(tmp_file) and (not overwrite_lock) and (not dry_run):
                        logger.info("Download's already existed: %s", title + '.' + oformat)
                        logger.info("视频已存在: %s", title + '.' + oformat)
                        count += 1
                        continue

                # use loaderCDN API to get downloadable response
                response = myloader.api_req(uri,headers=_headers)

                if response:
                    logger.info("Analyzing: %s, total %d/%d", uri, count+1, len(URLs))
                    logger.info("解析")
                    # parse and download requested file
                    parsed_response = myloader.parse_response_content(response)
                    content = parsed_response['content'] # an json object
                    head = parsed_response['headers'] # json object

                    # 下载开始
                    if not dry_run:
                        avail_formats = [x['format'] for x in content['formats']]
                        if oformat in avail_formats:
                            index = avail_formats.index(oformat)

                            if not title:
                                title,ext = content['formats'][index]['filename'].strip().split('.')

                            url = content['formats'][index]['url'].strip()
                            #if oformat == content['originalFormat']:  # this seems to cause some problems
                                #url = url + '&quality=' + str(quality)

                            logger.info("Downloading: %s", title + "." + ext)
                            logger.info("下载开始")
                            filepath = save_dir + os.path.sep + title

                            if not os.path.isdir(filepath):
                                os.makedirs(filepath)

                            filename = filepath + os.path.sep + title + '.' + oformat

                            if os.path.isfile(filename):
                                if overwrite_lock:
                                    backupfile = (filepath + os.path.sep + "backup-" + title
                                            + datetime.now().strftime('%Y-%m-%d-%H-%M') + '.'
                                            + oformat)
                                    shutil.move(filename, backupfile)
                                else:
                                    logger.warn("Download's already existed: %s", title + '.' + ext)
                                    logger.warn("视频已存在" + os.linesep)
                                    count += 1
                                    continue

                            try:
                                # add folder-tag: info.log
                                try:
                                    ftag = open(filepath + os.path.sep + 'info.log', 'wt', encoding='utf-8')
                                    ftag_str = title + os.linesep + subtitle + os.linesep + uri
                                    ftag.write(ftag_str)
                                    ftag.close()
                                except Exception as e:
                                    logger.warn(e)

                                size = 0
                                r = requests.get(url,headers=_headers,stream=True)
                                chunk_size = 512*1024 # 单次请求最大值
                                with open(filename,'wb') as f:
                                    try:
                                        for chunk in r.iter_content(chunk_size=chunk_size):
                                            if chunk:
                                                f.write(chunk)
                                                size += len(chunk)
                                                f.flush()
                                                sys.stdout.write('\b'*64 + 'Now: %d' % size)
                                                sys.stdout.flush()
                                    except http.client.IncompleteRead as e:
                                            f.write(e.partial)
                                            size += len(e.partial)
                                            f.flush()
                                            sys.stdout.write('\b'*64 + 'Now: %d' % size)
                                            sys.stdout.flush()
                            except Exception as e:
                                logger.exception(os.linesep + e + os.linesep)
                                sys.exit(1)

                            logger.info("Download finished")
                            logger.info("下载完毕")
                            # 要求格式不存在
                        else:
                            logger.warn("Requested format %s not available through loaderCDN", oformat)
                            logger.warn("loaderCDN暂不支持请求格式%s" + os.linesep, oformat)
                            continue
                    # Dry-run options
                    elif url_only:
                        f = open(save_dir + os.path.sep + content['title'] + '-real_urls.txt', 'w')
                        logger.info(content['title'])
                        for _format in content['formats']:
                            logger.info(_format['format'] + ": " +  _format['url'])
                            f.write(_format['format'] + ": " +  _format['url'])
                        f.close()
                    else:
                        #content.pop('formats',None)

                        content.pop('qualities',None)
                        pretty1 = json.dumps(head, indent=4,sort_keys=True, ensure_ascii=False)
                        logger.info(pretty1)
                        pretty2 = json.dumps(content, indent=4,sort_keys=True, ensure_ascii=False)
                        logger.info(pretty2)

                        try:
                            f = open(save_dir + os.path.sep + content['title'] + '-extract_details.txt', 'w', encoding='utf-8')
                            f.write(pretty1)
                            f.write(pretty2)
                            f.close()
                        except Exception as e:
                            logger.info(e)
                            continue
                time.sleep(5)
                count += 1

            if not dry_run and len(URLs) > 1:
                logger.info('List downloaded')
                logger.info('列表下载完成' + os.linesep)
    except Exception as e:
        logger.exception(e)
        sys.exit(1)

def main():

    parser = argparse.ArgumentParser(
        prog='loadercdn api',
        usage='lcddownloader -k key.txt -F mp3 url',
        add_help=False,
    )
    parser.add_argument(
        '-h', '--help', action='store_true',
        help='Print this help message and exit'
    )

    dry_run_grp = parser.add_argument_group(
        'Dry-run options', '(no actual downloading)'
    )
    dry_run_grp = dry_run_grp.add_mutually_exclusive_group()
    dry_run_grp.add_argument(
        '-i', '--info', action='store_true', help='Print extracted information (headers)'
    )
    dry_run_grp.add_argument(
        '-u', '--url', action='store_true',  help='Print extracted URLs (only)'
    )

    parser.add_argument(
        '-F', '--format', type=str,
        help='specify downloading format'
    )
    parser.add_argument(
        '-f', '--force', action='store_true',
        help='force overwrite existing file'
    )
    parser.add_argument(
        '-H', '--headers', metavar="HEADER_FILE",
        help='Load headers.txt'
    )
    parser.add_argument(
        '-I', '--input-file', metavar='FILE', type=argparse.FileType('r'),
        help='Read non-playlist URLs from FILE'
    )
    parser.add_argument(
        '-k', '--key', type=str,
        help='supply loadercdn api key: string or key.txt'
    )

    parser.add_argument(
        '-s', '--start', type=int,
        help='starting position of URLs list: 1-len(URLs)'
    )

    parser.add_argument(
        '-e', '--end', type=int,
        help='end position of URLs list: 1-len(URLs)'
    )

    parser.add_argument(
        '-d', '--debug', action='store_true',
        help='debug mode. Enables debug.log'
    )

    parser.add_argument('URL', nargs='*', help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.help:
        print()
        parser.print_help()
        sys.exit()

    global dry_run
    global custom_headers
    global oformat
    global quality
    global overwrite_lock

    url_only = args.url
    if args.info or args.url:
        dry_run = True

    if args.headers:
        load_headers(args.headers)

    if args.format:
        oformat = str(args.format)

    if args.force:
        overwrite_lock = True

    URLs = []
    if args.input_file:
        print("You are loading urls from %s", args.input_file)
        URLs.extend([x for x in args.input_file.read().splitlines() if x])
        global original_list_name
        original_list_name = str(args.input_file)

    URLs.extend(args.URL)

    if not URLs:
        parser.print_help()
        sys.exit()

    list_start = 1 if not args.start else args.start
    list_end = len(URLs) if not args.end else args.end

    if list_start > len(URLs) or list_end > len(URLs) or list_start > list_end or list_start <= 0:
        print("URLs list range error: start: %d, end: %d, length: %d" % (list_start, list_end, len(URLs)))
        sys.exit()

    URLs = URLs[list_start-1:list_end]
    global start_position
    start_position = list_start

    api_key = ""
    if not args.key:
        print("Please enter your loaderCDN api key: -k/--key api_key")
        sys.exit()
    else:
        if "key.txt" in args.key:
            with open("key.txt", 'r') as keyfile:
                api_key = keyfile.read().strip()
        else:
            api_key = args.key

    # Logging
    global logger
    if args.debug:
        logger = logging.getLogger("debug_logger")
        logger.info("debugging mode")
    else:
        logger = logging.getLogger()

    # welcome message
    print("================================================================================================================")
    print("Welcome to lcddownloader, a python wrapper for loadercdn.io url extraction service")
    print("Copyright: Video extraction service is provided by LoaderCDN @ 2018. The code merely wraps it in Python and provides a downloading function through requests.")
    print("Note: no continue-download function is provided through LoaderCDN. So please delete old download folders for incomplete download.")
    print("================================================================================================================")
    parser.print_help()
    print()


    try:
        myloader = loaderCDN()
        myloader.set_key(api_key)
        download_main(myloader, URLs, url_only=url_only ,oformat=oformat,quality=quality)
    except Exception as e:
        print(e)
        sys.exit(1)

if __name__ == '__main__':

    setup_logger()
    main()

