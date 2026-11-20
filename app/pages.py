"""Server-rendered pages. Plain HTML + a little JS, so there is no frontend build step."""
from html import escape

CSS = """
:root{--bg:#f3f5f7;--card:#fff;--ink:#14212b;--muted:#5a6b78;--line:#d9e0e6;--accent:#0f6e74;--mark:#ffe45c;--markink:#3a3000;--bad:#a8321e}
@media (prefers-color-scheme:dark){:root{--bg:#0b1217;--card:#121d25;--ink:#e6edf2;--muted:#93a5b2;--line:#24333e;--accent:#5cc4c9;--bad:#ff8a73;color-scheme:dark}}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:560px;margin:0 auto;padding:40px 16px 64px;display:grid;gap:20px}
main.wide{max-width:980px}
h1{font-size:1.9rem;line-height:1.15;margin:0}h2{font-size:1.15rem;margin:0}
p{margin:0}.muted{color:var(--muted)}.logo{font-weight:800;font-size:1.2rem;letter-spacing:-.02em}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;display:grid;gap:12px}
label{font-size:.85rem;color:var(--muted);display:grid;gap:4px}
input,select{font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink)}
button,.btn{font:600 .95rem system-ui,sans-serif;padding:11px 16px;border-radius:10px;border:0;background:var(--accent);color:#fff;cursor:pointer;text-decoration:none;text-align:center;display:inline-block}
button.ghost{background:none;color:var(--ink);border:1px solid var(--line);padding:6px 10px;font-weight:500;font-size:.8rem}
.code{font:700 1.8rem ui-monospace,Menlo,monospace;letter-spacing:.06em;background:var(--mark);color:var(--markink);border-radius:10px;padding:10px 14px;text-align:center;user-select:all}
ol{margin:0;padding-left:1.2em;display:grid;gap:6px}
.err{color:var(--bad)}.ok{color:var(--accent);font-weight:600}
table{width:100%;border-collapse:collapse;font-size:.88rem}th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.scroll{overflow-x:auto}.mono{font-family:ui-monospace,Menlo,monospace}
.pill{font-size:.72rem;border:1px solid var(--line);border-radius:99px;padding:1px 8px;white-space:nowrap}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:end}
"""


def page(title: str, body: str, wide: bool = False) -> str:
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{CSS}</style></head>"
        f"<body><main class='{'wide' if wide else ''}'><span class='logo'>stash</span>{body}</main></body></html>"
    )


def error_page(message: str) -> str:
    return page("Stash invite", f"<div class='card'><h1>Can't use this invite</h1><p class='err'>{escape(message)}</p></div>")


def invite_page(code: str, note: str, error: str = "") -> str:
    err = f"<p class='err'>{escape(error)}</p>" if error else ""
    who = f"<p class='muted'>Invite: {escape(note)}</p>" if note else ""
    return page("Join Stash", f"""
<h1>You're invited to Stash</h1>
<p class='muted'>Stash organises the reels and posts you save on Instagram. You send a reel to @stash in DMs, and it gets sorted, searchable and resurfaced.</p>
{who}
<form class='card' method='post' action='/i/{escape(code)}'>
  <h2>Step 1 · Your details</h2>
  <label for='name'>Name<input id='name' name='name' required maxlength='60' autocomplete='given-name'></label>
  <label for='email'>Email (optional, for account recovery)<input id='email' name='email' type='email' maxlength='120'></label>
  {err}
  <button type='submit'>Accept invite</button>
</form>""")


def welcome_page(name: str, link_code: str, expires_at: str, ig_username: str, linked: bool, token: str) -> str:
    if linked:
        return page("Stash is ready", f"""
<h1>You're all set, {escape(name)}</h1>
<div class='card'><p class='ok'>Instagram linked ✓</p>
<p>From now on, on any reel: tap the paper plane → <b>@{escape(ig_username)}</b> → Send. You'll get a reply like “Saved to Recipes ✓”.</p>
<a class='btn' href='/library?t={escape(token)}'>Open my library</a></div>""")
    return page("Link Instagram", f"""
<h1>Step 2 · Link your Instagram</h1>
<p class='muted'>Send this code to @{escape(ig_username)} in an Instagram DM, from the account you save reels on.</p>
<div class='card'>
  <div class='code' id='code'>{escape(link_code)}</div>
  <button class='ghost' id='copy' type='button'>Copy code</button>
  <ol>
    <li>Copy the code.</li>
    <li>Open <a href='https://ig.me/m/{escape(ig_username)}' target='_blank' rel='noopener'>ig.me/m/{escape(ig_username)}</a> (opens Instagram DMs).</li>
    <li>Paste the code and send it.</li>
  </ol>
  <p class='muted' style='font-size:.85rem'>Code expires at <span class='mono'>{escape(expires_at[11:16])} UTC</span>. Reload this page for a new one.</p>
  <p id='status' class='muted'>Waiting for your DM…</p>
</div>
<script>
document.getElementById('copy').onclick=async()=>{{const t=document.getElementById('code').textContent;
 try{{await navigator.clipboard.writeText(t);copy.textContent='Copied'}}catch(e){{getSelection().selectAllChildren(document.getElementById('code'))}}}};
setInterval(async()=>{{try{{const r=await fetch('/api/me?t={escape(token)}');const j=await r.json();if(j.linked)location.reload()}}catch(e){{}}}},4000);
</script>""")


def _save_row(s: dict) -> str:
    caption = escape(s["caption"][:120]) or "<span class='muted'>(no caption)</span>"
    link = f"<a href='{escape(s['url'])}' target='_blank' rel='noopener'>Open</a>" if s["url"] else ""
    return (f"<tr><td>{caption}</td><td><span class='pill'>{escape(s['kind'])}</span></td>"
            f"<td>{link}</td><td class='muted mono'>{escape(s['created_at'][:10])}</td></tr>")


def library_page(name: str, saves: list[dict]) -> str:
    if not saves:
        body = "<div class='card'><p>No saves yet. Send a reel to @stash in Instagram DMs and it shows up here.</p></div>"
    else:
        groups: dict[str, list[dict]] = {}
        for s in saves:
            groups.setdefault(s["category"] or "Processing…", []).append(s)
        body = ""
        for cat, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            rows = "".join(_save_row(s) for s in items)
            body += f"<div class='card'><h2>{escape(cat)} <span class='muted'>· {len(items)}</span></h2><div class='scroll'><table>{rows}</table></div></div>"
    return page("My Stash", f"<h1>{escape(name)}'s Stash</h1><p class='muted'>{len(saves)} saves</p>{body}", wide=True)


ADMIN_HTML = page("Stash admin", """
<h1>Admin</h1>
<div class='card' id='login'>
  <label for='tok'>Admin token<input id='tok' type='password' autocomplete='off'></label>
  <button id='go' type='button'>Sign in</button><p id='lerr' class='err'></p>
</div>
<div id='app' hidden style='display:grid;gap:20px'>
  <div class='card'><h2>Create invite</h2>
    <div class='row'>
      <label for='note'>Who is it for<input id='note' placeholder='e.g. Priya from college'></label>
      <label for='uses'>Uses<input id='uses' type='number' min='1' value='1' style='width:80px'></label>
      <label for='days'>Expires in (days)<input id='days' type='number' min='1' value='14' style='width:100px'></label>
      <button id='create' type='button'>Create</button>
    </div>
    <p id='newlink' class='mono'></p>
  </div>
  <div class='card'><h2>Invites</h2><div class='scroll'><table id='inv'></table></div></div>
  <div class='card'><h2>Members</h2><div class='scroll'><table id='users'></table></div></div>
  <div class='card'><h2>Waitlist</h2><p class='muted'>People who DMed @stash without an invite and replied WAITLIST.</p><div class='scroll'><table id='wait'></table></div></div>
</div>
<script>
let TOKEN='';try{TOKEN=sessionStorage.getItem('stash_admin')||''}catch(e){}
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,opts={}){const r=await fetch(path,{...opts,headers:{'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'}});
 if(r.status===401)throw new Error('Wrong admin token.');if(!r.ok)throw new Error(await r.text());return r.json()}
async function load(){
 const [inv,users,wait]=await Promise.all([api('/api/admin/invites'),api('/api/admin/users'),api('/api/admin/waitlist')]);
 $('inv').innerHTML='<tr><th>Code</th><th>For</th><th>Used</th><th>Expires</th><th>Link</th><th></th></tr>'+inv.map(i=>`<tr><td class=mono>${esc(i.code)}</td><td>${esc(i.note)}</td><td>${i.uses}/${i.max_uses}</td><td class=mono>${esc((i.expires_at||'never').slice(0,10))}</td><td class=mono style="font-size:.75rem">${esc(i.url)}</td><td>${i.revoked?'<span class=pill>cancelled</span>':`<button class=ghost data-rv="${esc(i.code)}">Cancel</button>`}</td></tr>`).join('');
 $('users').innerHTML='<tr><th>Name</th><th>Instagram</th><th>Saves</th><th>Invite</th><th>Status</th><th></th></tr>'+users.map(u=>`<tr><td>${esc(u.name)}</td><td>${u.igsid?'<span class=ok>linked</span>':'<span class=muted>not linked</span>'}</td><td>${u.saves}</td><td class=mono>${esc(u.invite_code)}</td><td>${esc(u.status)}</td><td><button class=ghost data-u="${u.id}" data-s="${u.status==='active'?'revoked':'active'}">${u.status==='active'?'Turn off':'Turn on'}</button></td></tr>`).join('');
 $('wait').innerHTML='<tr><th>Instagram ID</th><th>Joined</th><th></th></tr>'+wait.map(w=>`<tr><td class=mono>${esc(w.igsid)}</td><td class=mono>${esc(w.created_at.slice(0,10))}</td><td>${w.invited?'<span class=pill>invited</span>':`<button class=ghost data-w="${esc(w.igsid)}">Send invite by DM</button>`}</td></tr>`).join('');
}
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{
 if(b.dataset.rv){await api(`/api/admin/invites/${b.dataset.rv}/revoke`,{method:'POST'});load()}
 if(b.dataset.u){await api(`/api/admin/users/${b.dataset.u}/status`,{method:'POST',body:JSON.stringify({status:b.dataset.s})});load()}
 if(b.dataset.w){await api(`/api/admin/waitlist/${b.dataset.w}/invite`,{method:'POST'});load()}
}catch(err){alert(err.message)}});
$('create').onclick=async()=>{const j=await api('/api/admin/invites',{method:'POST',body:JSON.stringify({note:$('note').value,max_uses:+$('uses').value||1,expires_in_days:+$('days').value||null})});
 $('newlink').textContent='Send this link: '+j.url;$('note').value='';load()};
async function signin(){TOKEN=$('tok').value||TOKEN;try{await load();try{sessionStorage.setItem('stash_admin',TOKEN)}catch(e){}$('login').hidden=true;$('app').hidden=false}catch(e){$('lerr').textContent=e.message}}
$('go').onclick=signin;if(TOKEN)signin();
</script>""", wide=True)
