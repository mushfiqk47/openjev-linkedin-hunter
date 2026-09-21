CONNECTIONS_LINKS_JS = """
import json, time

js("window.location.href = '__CONNECTIONS_URL__'")
time.sleep(2.5)

for i in range(25):
    ready = js('''(() => {
        return document.querySelectorAll('a[aria-label^="Send a message"]').length > 0;
    })()''')
    if ready:
        break
    time.sleep(0.5)

for i in range(4):
    js('''(() => {
        const main = document.querySelector('main') || document.body;
        if (main) main.scrollTop = main.scrollHeight;
        window.scrollTo(0, document.body.scrollHeight);
        return true;
    })()''')
    time.sleep(0.8)

links = js('''(() => {
    const out = [];
    document.querySelectorAll('a').forEach(a => {
        const label = a.getAttribute('aria-label') || '';
        if (label.startsWith('Send a message')) {
            out.push({ label: label, href: a.getAttribute('href') });
        }
    });
    return out;
})()''')
print("LINKS:" + json.dumps(links))
"""

SEARCH_SWEEP_JS = """
import json, time

js("window.location.href = '__SEARCH_URL__'")
time.sleep(2.5)

for i in range(25):
    ready = js('''(() => {
        const main = document.querySelector('main');
        return !!(main && (main.querySelector('a[href*="/in/"]') || main.innerText.indexOf('No results') !== -1));
    })()''')
    if ready:
        break
    time.sleep(0.5)

js('''(() => { window.scrollTo(0, document.body.scrollHeight / 2); return true; })()''')
time.sleep(0.8)
js('''(() => { window.scrollTo(0, document.body.scrollHeight); return true; })()''')
time.sleep(0.8)

cards = js('''(() => {
    const main = document.querySelector('main') || document.body;
    const anchors = Array.from(main.querySelectorAll('a[href*="/in/"]'));
    const results = [];
    const seenHrefs = new Set();
    const nl = String.fromCharCode(10);

    anchors.forEach(a => {
        let href = (a.getAttribute('href') || '').split('?')[0];
        let rawText = (a.innerText || '').trim();
        if (href.includes('/in/') && !href.endsWith('/in/') && !href.endsWith('/in/me/') && !href.includes('/opportunities/')) {
            if (!seenHrefs.has(href)) {
                seenHrefs.add(href);
                let lines = rawText.split(nl).map(s => s.trim()).filter(Boolean);
                let name = '';
                let nameIdx = -1;
                for (let li = 0; li < lines.length; li++) {
                    let clean = lines[li].replace('• 1st', '').replace('• 2nd', '').replace('• 3rd+', '').trim();
                    if (clean && !clean.toLowerCase().includes('mutual connection') && !clean.toLowerCase().includes('student') && !clean.toLowerCase().includes('designer') && !clean.toLowerCase().includes('developer') && !clean.toLowerCase().includes('see open roles') && !clean.toLowerCase().includes('open to work')) {
                        name = clean;
                        nameIdx = li;
                        break;
                    }
                }
                if (!name && lines.length > 0) {
                    name = lines[0].replace('• 1st', '').trim();
                    nameIdx = 0;
                }
                let headline = '';
                if (nameIdx !== -1) {
                    for (let lj = nameIdx + 1; lj < lines.length && !headline; lj++) {
                        let l = lines[lj];
                        if (l.startsWith('•') || l === name) continue;
                        if (l.toLowerCase().includes('mutual connection') || l.toLowerCase().includes('follower')) continue;
                        headline = l;
                    }
                }
                if (name) {
                    results.push({ name: name, headline: headline, profile_url: href });
                }
            }
        }
    });
    return results;
})()''')

print(\"__MARKER__\" + json.dumps(cards))
"""

def search_page_url(page):
    return f"https://www.linkedin.com/search/results/people/?network=%5B%22F%22%5D&page={page}"

