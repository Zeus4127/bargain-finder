const CACHE='bf-site-v10';
const CORE=['./','./index.html','./deals.html','./app.html','./caravan.html','./manifest.webmanifest','./boot.js','./guide.js','./sales.js','./engine.js','./alerts.js','./vision.js','./web.js','./web.css','./flippro.html','./flippro.js','./undermarket.js','./dealtest.js','./flippro-page.js','./pro.css'];
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)))});
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE&&k!=='bf-shared').map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method==='POST'&&u.pathname.endsWith('/share')){
    e.respondWith((async()=>{const f=await e.request.formData();const c=await caches.open('bf-shared');
      const shots=f.getAll('shots').filter(x=>x&&x.size);await Promise.all(shots.map((x,i)=>c.put('./shared/'+Date.now()+'-'+i,new Response(x,{headers:{'Content-Type':x.type||'image/png'}}))));
      const p=new URLSearchParams();['title','text','url'].forEach(k=>{const v=f.get(k);if(v)p.set(k,v)});if(shots.length)p.set('shared','1');
      return Response.redirect('./app.html?'+p.toString(),303)})());return}
  if(e.request.method!=='GET'||/\.(apk|mp4)$/.test(u.pathname))return;   // big files and videos stream from the web, never cached
  e.respondWith(fetch(e.request).then(r=>{if(r.ok&&u.origin===location.origin){const c2=r.clone();caches.open(CACHE).then(c=>c.put(e.request,c2))}return r}).catch(()=>caches.match(e.request,{ignoreSearch:true})));
});
