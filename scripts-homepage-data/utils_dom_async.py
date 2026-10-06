"""Utils specifically for traversing the DOM with playwright"""
from playwright.sync_api import Locator, Page
from playwright_dompath.dompath_async import css_path, xpath_path
from typing import List, Dict, Union
from urllib.parse import urlparse, ParseResult
import tldextract
import re
from collections import defaultdict
from more_itertools import unique_everseen

from asyncstdlib.builtins import sorted, filter
from asyncstdlib.builtins import list as async_list
from asyncstdlib.builtins import map as async_map

DOMAIN_BLACKLIST = [
    "google",
    "twitter",
    "facebook",
    "doubleclick",
    "eventbrite",
    "youtube",
    "vimeo",
    "instagram",
    "ceros"
]

SUBDOMAIN_BLACKLIST = [
    "careers",
    "mail",
    "account",
    "events",
]

parents_cache = {}
href_cache = {}
async def get_parents(node: Locator, i: int = None) -> List[Locator]:
    """Given a child element in the DOM, return the path from ROOT to the child."""
    async def _get_parents(node: Locator) -> List[Locator]:
        all_parents = []
        p = [node]
        while len(p) != 0: # this is the cue for the top-most node
            p = p[0]
            all_parents.append(p)
            p = await p.locator('xpath=..').all()
        return all_parents[::-1]
    if i is None:
        return await _get_parents(node)
    else:
        global parents_cache
        if i not in parents_cache:
            parents_cache[i] = await _get_parents(node)
        return parents_cache[i]


async def nodes_are_equal(node_1: Locator, node_2: Locator) -> bool:
    """
    Check if two nodes are equal, by checking XPath.
    """
    node_1_xpath = await xpath_path(node_1)
    node_2_xpath = await xpath_path(node_2)
    return node_1_xpath == node_2_xpath


async def get_common_parent(node_1: Locator, node_2: Locator, return_common: bool = True) -> Locator:
    """Given two nodes in the DOM, return the common parent between them.
        * node_1: the target node
        * node_2: the comparator node
        * return_common (bool):
            * if true, return the first node that they both share.
            * if false, return the first node BEFORE the shared node, in the target node.
    """
    parents_1 = await get_parents(node_1)
    parents_2 = await get_parents(node_2)

    eq = await nodes_are_equal(parents_1[0], parents_2[0])
    if not eq:
        raise "No common ancestor!"

    for i in range(len(parents_1)):
        eq = await nodes_are_equal(parents_1[i], parents_2[i])
        if not eq:
            if return_common:
                return parents_1[i - 1]
            else:
                return parents_1[i]


async def is_smaller_child(child_candidate: Locator, parent_candidate: Locator) -> bool:
    """Given two nodes (in the same hierarchy), return:
        true if the "child_candidate" is a child of the "parent_candidate",
        false otherwise."""

    child_parents = await get_parents(child_candidate)
    parent_candidate = await get_parents(parent_candidate)
    return len(child_parents) > len(parent_candidate)


async def get_href(a: Locator = None, i: int = None) -> str:
    if a is not None:
        return await a.evaluate('a => a.href')
    if i is not None:
        if i not in href_cache:
            href_cache[i] = await a.evaluate('a => a.href')
        return href_cache[i]


async def get_highest_singular_parent(i: int, a_links: List[Locator]) -> Locator:
    """
    Get the largest possible bounding box in the DOM hierarchy that doesn't have any other links.

    params:
        * i: the index of node "a" in "a_links"
        * as: an Array of all DOM elements of type "A"
    """
    a = a_links[i]
    curr_parent = await get_parents(a)
    curr_parent = curr_parent[0]
    for j in range(len(a_links)):
        href_i = await get_href(a_links[i])
        href_j = await get_href(a_links[j])
        if (i != j) and (href_i != href_j):
            common_not_parent = await get_common_parent(a, a_links[j], return_common=False)
            cond = await is_smaller_child(common_not_parent, curr_parent)
            if cond:
                curr_parent = common_not_parent
    return curr_parent


async def get_text_of_node(node: Locator) -> str:
    return node.evaluate("""node => {
        var iter = document.createNodeIterator(node, NodeFilter.SHOW_TEXT)
        var textnode;
        var output_text = ''
    
        // print all text nodes
        while (textnode = iter.nextNode()) {
          output_text = output_text + ' ' + textnode.textContent
        }
        return output_text.trim()
    }""")


def is_banned_host(url: ParseResult) -> bool:
    host = url.netloc
    domain_parse = tldextract.extract(host)
    if domain_parse.domain not in DOMAIN_BLACKLIST:
        return True

    subdomain = domain_parse.subdomain.replace('www.', '')
    if subdomain not in SUBDOMAIN_BLACKLIST:
        return True

    return False


def get_valid_url(href: str, hostname: str =None):
    """Constructs a URL class out of a href. Flexible in case the href is just the path."""
    url = urlparse(href)
    if url.netloc == '':
        url = urlparse(hostname + href)

    return url


def get_url_parts(href: str, hostname: str = None):
    url = get_valid_url(href, hostname)
    if is_banned_host(url):
        return False

    path = url.path
    path_parts = re.split('[-/:.]', path)
    path_parts = list(filter(lambda x: x != '', path_parts))
    return len(path_parts) > 5


async def get_top_divs_from_page(page: Page):
    """Extract all `<a>` tags and follow them up the DOM tree to get the highest link.

    page: Playwright object representing the page.
    """
    all_as = await page.locator('a').all()

    # filter out <a> tags without a href
    all_as = await async_list(filter(lambda x: get_href(x) is not None, all_as))

    a_top_nodes = []
    for i, _ in enumerate(all_as):
        highest_parent = await get_highest_singular_parent(i, all_as)
        a_top_nodes.append(highest_parent)
    return a_top_nodes


async def get_node_name(loc: Locator) -> str:
    return await loc.evaluate('e => e.nodeName')


async def get_css_attrs(node: Locator) -> Dict[str, str]:
    css_attrs = await node.evaluate('''node => getComputedStyle(node)''')
    return dict(filter(lambda x: not x[0].isdigit(), css_attrs.items()))


async def get_img_attrs(node: Locator) -> List[Dict[str, Union[str, int]]]:
    output_img_data = []
    imgs = await node.locator('img').all()
    for img in imgs:
        output = {}
        bb_img = await img.bounding_box()
        output['img_x'] = bb_img['x']
        output['img_y'] = bb_img['y']
        output['img_width'] = bb_img['width']
        output['img_height'] = bb_img['height']
        output['img_src'] = await img.evaluate('''node => node.src''')
        output['img_text'] = await img.evaluate('''node => node.alt.trim()''')
        output_img_data.append(output)
    return output_img_data


async def get_bounding_box_info(page: Page) -> List[Dict[str, Union[str, int]]]:
    """
    Takes in a page and extracts key information about parts of the page. Key information includes:
        * Bounding boxes for all upper-divs encircling links
        * Images (if any) in the same upper-divs as links
        * Text content associated with any links.

    :param page:
    :return:
    """

    # get page width and page height
    page_width = await page.evaluate('''
        Math.max(
            document.documentElement["clientWidth"],
            document.body["scrollWidth"],
            document.documentElement["scrollWidth"],
            document.body["offsetWidth"],
            document.documentElement["offsetWidth"]
        );
    ''')

    page_height = await page.evaluate('''Math.max(
        document.documentElement["clientHeight"],
        document.body["scrollHeight"],
        document.documentElement["scrollHeight"],
        document.body["offsetHeight"],
        document.documentElement["offsetHeight"]
    );''')

    # process for each link
    all_links = []
    top_nodes_of_links = await get_top_divs_from_page(page)
    for node in top_nodes_of_links:
        # general data
        node_text = await get_text_of_node(node)
        css_attrs = await get_css_attrs(node)

        # get links and filter to a set of conditions
        links = await node.locator('a').all()
        if (len(links) == 0) and (get_node_name(node) == 'A'):
            links = [node]

        links = await async_list(async_map(lambda x: {'a': x, 'text': get_text_of_node(x), 'href': get_href(x)}, links))
        links = await sorted(links, key=lambda x: -len(x['text']))  # links with the most text first
        links = list(unique_everseen(links, key=lambda x: x['href']))
        # iterate through links and get information
        for link in links:
            output = {}
            a = link['a']
            bb = await a.bounding_box()
            output['x'] = bb['x']
            output['y'] = bb['y']
            output['width'] = bb['width']
            output['height'] = bb['height']
            output['page_width'] = page_width
            output['page_height'] = page_height
            output['href'] = link['href']
            output['link_text'] = link['text']
            output['all_text'] = node_text
            output['css_attributes'] = css_attrs
            output['img'] = await get_img_attrs(a)
            all_links.append(output)

    deduplicated = unique_everseen(all_links, key=lambda x: (x['href'], x['x'], x['y']))
    return list(deduplicated)


async def spotcheck_draw_bounding_box(loc: Locator) -> None:
    """To spotcheck, draw bounding boxes on the page. Only useful if you're not in headless mode."""
    await loc.evaluate("node => node.setAttribute('style', 'border: 4px dotted blue !important;')"),
