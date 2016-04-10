"""Ghost Buster. Static site generator for Ghost.

Usage:
  buster.py setup [--gh-repo=<repo-url>] [--dir=<path>]
  buster.py generate [--localhost=<local-address>] [--public=<public-domain>] [--dir=<path>]
  buster.py preview [--dir=<path>]
  buster.py deploy [--dir=<path>] [--date=<date>]
  buster.py add-domain <domain-name> [--dir=<path>]
  buster.py (-h | --help)
  buster.py --version

Options:
  -h --help                    Show this screen.
  --version                    Show version.
  --dir=<path>                 Absolute path of directory to store static pages.
  --localhost=<local-address>  Address of local ghost installation [default: localhost:2368].
  --public=<public-domain>     The public domain name of the blog.
  --gh-repo=<repo-url>         URL of your gh-pages repository.
  --date=<date>                Set author date and commiter date of the commit
"""

import os
import re
import sys
import fnmatch
import shutil
import SocketServer
import SimpleHTTPServer
from docopt import docopt
from time import localtime, strftime
from datetime import datetime
from git import Repo
from pyquery import PyQuery
from dateutil.tz import tzlocal


def main():
    arguments = docopt(__doc__, version='0.1.3')
    if arguments['--dir'] is not None:
        static_path = arguments['--dir']
    else:
        static_path = os.path.join(os.getcwd(), 'static')

    if arguments['generate']:
        command = ("wget "
                   "--recursive "             # follow links to download entire site
                   "--convert-links "         # make links relative
                   "--page-requisites "       # grab everything: css / inlined images
                   "--no-parent "             # don't go to parent level
                   "--directory-prefix {1} "  # download contents to static/ folder
                   "--no-host-directories "   # don't create domain named folder
                   "--restrict-file-name=unix "  # don't escape query string
                   "{0}").format(arguments['--localhost'], static_path)
        os.system(command)

        # remove query string since Ghost 0.4
        file_regex = re.compile(r'.*?(\?.*)')
        for root, dirs, filenames in os.walk(static_path):
            for filename in filenames:
                if file_regex.match(filename):
                    newname = re.sub(r'\?.*', '', filename)
                    print "Rename", filename, "=>", newname
                    os.rename(os.path.join(root, filename), os.path.join(root, newname))

        # remove superfluous "index.html" from relative hyperlinks found in text
        abs_url_regex = re.compile(r'^(?:[a-z]+:)?//', flags=re.IGNORECASE)
        def fixLinks(text, parser):
            d = PyQuery(bytes(bytearray(text, encoding='utf-8')), parser=parser)
            for element in d('a'):
                e = PyQuery(element)
                href = e.attr('href')
                if not abs_url_regex.search(href):
                    new_href = re.sub(r'/index\.html$', '/', href)
                    new_href = re.sub(r'index.html#', '#', new_href)
                    new_href = re.sub(r'index.html', '/', new_href)
                    e.attr('href', new_href)
                    print "\t", href, "=>", new_href
            if parser == 'html':
                return d.html(method='html').encode('utf8')
            return d.__unicode__().encode('utf8')

        # fix links in all html files
        for root, dirs, filenames in os.walk(static_path):
            for filename in fnmatch.filter(filenames, "*.html"):
                filepath = os.path.join(root, filename)
                parser = 'html'
                if root.endswith("/rss"):  # rename rss index.html to index.xml
                    parser = 'xml'
                    newfilepath = os.path.join(root, os.path.splitext(filename)[0] + ".xml")
                    os.rename(filepath, newfilepath)
                    filepath = newfilepath
                with open(filepath) as f:
                    filetext = f.read().decode('utf8')
                print "fixing links in ", filepath
                newtext = fixLinks(filetext, parser)
                with open(filepath, 'w') as f:
                    f.write(newtext)

        # replace local url with public blog url
        if arguments['--public'] is not None:
            print "replace", arguments['--localhost'], "with", arguments['--public']
            for root, dirs, filenames in os.walk(static_path):
                if '.git' in dirs:
                    dirs.remove('.git')
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    with open(filepath) as f:
                        filetext = f.read()
                    newtext = filetext.replace(arguments['--localhost'],
                            arguments['--public'])
                    with open(filepath, "w") as f:
                        f.write(newtext)

    elif arguments['preview']:
        os.chdir(static_path)

        Handler = SimpleHTTPServer.SimpleHTTPRequestHandler
        httpd = SocketServer.TCPServer(("", 9000), Handler)

        print "Serving at port 9000"
        # gracefully handle interrupt here
        httpd.serve_forever()

    elif arguments['setup']:
        if arguments['--gh-repo']:
            repo_url = arguments['--gh-repo']
        else:
            repo_url = raw_input("Enter the Github repository URL:\n").strip()

        # Create a fresh new static files directory
        if os.path.isdir(static_path):
            confirm = raw_input("This will destroy everything inside static/."
                                " Are you sure you want to continue? (y/N)").strip()
            if confirm != 'y' and confirm != 'Y':
                sys.exit(0)
            shutil.rmtree(static_path)

        # User/Organization page -> master branch
        # Project page -> gh-pages branch
        branch = 'gh-pages'
        regex = re.compile(".*[\w-]+\.github\.(?:io|com).*")
        if regex.match(repo_url):
            branch = 'master'

        # Prepare git repository
        repo = Repo.init(static_path)
        git = repo.git

        if branch == 'gh-pages':
            git.checkout(b='gh-pages')
        repo.create_remote('origin', repo_url)

        # Add README
        file_path = os.path.join(static_path, 'README.md')
        with open(file_path, 'w') as f:
            f.write('# Blog\nPowered by [Ghost](http://ghost.org) and [Buster](https://github.com/invictusjs/buster/).\n')

        print "All set! You can generate and deploy now."

    elif arguments['deploy']:
        repo = Repo(static_path)
        repo.git.add('.')

        current_time = strftime("%Y-%m-%d %H:%M:%S", localtime())
        if arguments['--date'] is not None:
            datetimeObj = datetime.strptime(arguments['--date'], "%Y-%m-%d %H:%M:%S")
            datetimeObj = datetimeObj.replace(tzinfo=tzlocal())
            current_time_with_tz = datetimeObj.strftime("%Y-%m-%d %H:%M:%S %z")

            os.environ["GIT_AUTHOR_DATE"] = current_time_with_tz
            os.environ["GIT_COMMITTER_DATE"] = current_time_with_tz
            current_time = datetimeObj.strftime("%Y-%m-%d %H:%M:%S")

        repo.index.commit('Blog update at {}'.format(current_time))

        origin = repo.remotes.origin
        repo.git.execute(['git', 'push', '-u', origin.name,
                         repo.active_branch.name])
        print "Good job! Deployed to Github Pages."

    elif arguments['add-domain']:
        repo = Repo(static_path)
        custom_domain = arguments['<domain-name>']

        file_path = os.path.join(static_path, 'CNAME')
        with open(file_path, 'w') as f:
            f.write(custom_domain + '\n')

        print "Added CNAME file to repo. Use `deploy` to deploy"

    else:
        print __doc__

if __name__ == '__main__':
    main()
