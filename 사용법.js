  (function(){
    var root=document.documentElement, btn=document.getElementById('themebtn'),
        label=document.getElementById('themelabel'), icon=document.getElementById('themeicon');
    var SUN='<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>';
    var MOON='<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>';
    function apply(t){ root.setAttribute('data-theme',t);
      label.textContent = t==='dark' ? '밝은 테마' : '어두운 테마';
      icon.innerHTML = t==='dark' ? SUN : MOON; }
    var saved='light'; try{ saved=localStorage.getItem('bibleclip-guide-theme')||'light'; }catch(e){}
    apply(saved);
    btn.addEventListener('click',function(){
      var t = root.getAttribute('data-theme')==='dark' ? 'light' : 'dark';
      apply(t); try{ localStorage.setItem('bibleclip-guide-theme',t); }catch(e){}
    });
  })();
  (function(){
    var links=[].slice.call(document.querySelectorAll('#nav a.navlink'));
    var map={}; links.forEach(function(a){ map[a.getAttribute('href').slice(1)]=a; });
    var io=new IntersectionObserver(function(entries){
      entries.forEach(function(en){
        if(en.isIntersecting){ links.forEach(function(a){a.classList.remove('active');});
          var a=map[en.target.id]; if(a)a.classList.add('active'); }
      });
    },{rootMargin:'-45% 0px -50% 0px',threshold:0});
    document.querySelectorAll('section.sec').forEach(function(s){io.observe(s);});
  })();
