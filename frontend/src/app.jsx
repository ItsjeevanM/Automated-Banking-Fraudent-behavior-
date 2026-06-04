import { useState, useEffect, useRef } from "react";

/* ─────────────────────────────────────────────
   GLOBAL STYLES
───────────────────────────────────────────── */
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500&display=swap');
  *, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }
  :root {
    --bg:#040d1a; --bg2:#071428; --surface:#0a1f3d; --surface2:#0f2a50;
    --teal:#00d4aa; --teal2:#00b894; --amber:#f59e0b; --red:#ef4444; --blue:#3b82f6;
    --text:#e8f0fe; --muted:#6b82a8; --border:rgba(0,212,170,0.15);
    --glow:0 0 40px rgba(0,212,170,0.15);
    --fd:'Syne',sans-serif; --fm:'JetBrains Mono',monospace; --fb:'DM Sans',sans-serif;
  }
  body { background:var(--bg); color:var(--text); font-family:var(--fb); overflow-x:hidden; -webkit-font-smoothing:antialiased; }
  ::-webkit-scrollbar{width:5px} ::-webkit-scrollbar-track{background:var(--bg)} ::-webkit-scrollbar-thumb{background:var(--surface2);border-radius:3px}
  @keyframes fadeUp { from{opacity:0;transform:translateY(22px)} to{opacity:1;transform:translateY(0)} }
  @keyframes fadeIn { from{opacity:0} to{opacity:1} }
  @keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-13px)} }
  @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(.7)} }
`;

/* ─────────────────────────────────────────────
   SHARED COMPONENTS
───────────────────────────────────────────── */
function SectionLabel({ children, style = {} }) {
  return (
    <div style={{ fontFamily:"var(--fm)", fontSize:"0.7rem", color:"var(--teal)", textTransform:"uppercase", letterSpacing:"0.12em", marginBottom:16, display:"flex", alignItems:"center", gap:10, ...style }}>
      <span style={{ display:"block", width:28, height:1, background:"var(--teal)" }} />
      {children}
    </div>
  );
}

function Btn({ children, onClick, variant = "primary", style = {} }) {
  const base = { border:"none", cursor:"pointer", fontFamily:"var(--fb)", fontWeight:600, fontSize:"0.92rem", borderRadius:8, padding:"13px 28px", transition:"all .2s", display:"flex", alignItems:"center", gap:8, ...style };
  const styles = variant === "primary"
    ? { ...base, background:"var(--teal)", color:"#040d1a" }
    : { ...base, background:"transparent", color:"var(--text)", border:"1px solid var(--border)" };
  return (
    <button style={styles} onClick={onClick}
      onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = variant === "primary" ? "0 8px 24px rgba(0,212,170,.3)" : "none"; if (variant !== "primary") { e.currentTarget.style.borderColor = "var(--teal)"; e.currentTarget.style.color = "var(--teal)"; } }}
      onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; if (variant !== "primary") { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--text)"; } }}
    >{children}</button>
  );
}

/* ─────────────────────────────────────────────
   NAV
───────────────────────────────────────────── */
function Nav({ page, setPage }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const el = document.getElementById("page-scroll");
    if (!el) return;
    const onScroll = () => setScrolled(el.scrollTop > 30);
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  const links = [["Overview","hero"],["Workflow","workflow"],["Features","features"],["Analyze","upload"]];
  return (
    <nav style={{ position:"fixed", top:0, left:0, right:0, zIndex:100, display:"flex", alignItems:"center", justifyContent:"space-between", padding:"18px 48px", background: scrolled ? "rgba(4,13,26,.97)" : "linear-gradient(to bottom,rgba(4,13,26,.95),transparent)", backdropFilter:"blur(14px)", borderBottom: scrolled ? "1px solid var(--border)" : "1px solid transparent", transition:"all .3s" }}>
      <div onClick={() => setPage("hero")} style={{ fontFamily:"var(--fd)", fontWeight:800, fontSize:"1.3rem", letterSpacing:"-0.03em", color:"var(--text)", display:"flex", alignItems:"center", gap:10, cursor:"pointer" }}>
        <div style={{ width:32, height:32, background:"linear-gradient(135deg,var(--teal),#0066ff)", borderRadius:8, display:"flex", alignItems:"center", justifyContent:"center", fontFamily:"var(--fm)", fontSize:"0.78rem", fontWeight:700, color:"#040d1a" }}>BF</div>
        BankForensiq
      </div>
      <div style={{ display:"flex", alignItems:"center", gap:28 }}>
        {links.map(([label, p]) => (
          <button key={p} onClick={() => setPage(p)} style={{ background:"none", border:"none", cursor:"pointer", fontFamily:"var(--fb)", fontSize:"0.88rem", fontWeight:500, color: page === p ? "var(--teal)" : "var(--muted)", transition:"color .2s", letterSpacing:"0.02em" }}>{label}</button>
        ))}
        <button onClick={() => setPage("upload")} style={{ background:"var(--teal)", color:"#040d1a", padding:"9px 20px", borderRadius:7, border:"none", cursor:"pointer", fontFamily:"var(--fb)", fontWeight:600, fontSize:"0.86rem", transition:"all .2s" }}
          onMouseEnter={e => { e.currentTarget.style.background = "var(--teal2)"; e.currentTarget.style.transform = "translateY(-1px)"; }}
          onMouseLeave={e => { e.currentTarget.style.background = "var(--teal)"; e.currentTarget.style.transform = ""; }}>
          Upload Statement
        </button>
      </div>
    </nav>
  );
}

/* ─────────────────────────────────────────────
   PAGE 1: HERO
───────────────────────────────────────────── */
const txns = [
  { merchant:"GAS FILLING STATION", meta:"2023-07-26 · CARD", amount:"−₹500.00", dc:"debit" },
  { merchant:"UPI/3234", meta:"2023-08-22 · UPI", amount:"−₹3,000.00", dc:"debit" },
  { merchant:"NEFT / Salary", meta:"2024-01-02 · NEFT", amount:"+₹15,000.00", dc:"credit" },
  { merchant:"ATM / 5188810", meta:"2023-08-07 · ATM", amount:"−₹1,000.00", dc:"debit" },
];
const heroStats = [{ v:"0–100", l:"Risk Score" },{ v:"8", l:"AI Models" },{ v:"3", l:"File Formats" },{ v:"7", l:"Pipeline Steps" }];

function HeroPage({ setPage }) {
  return (
    <section style={{ minHeight:"100vh", display:"flex", flexDirection:"column", justifyContent:"center", padding:"140px 48px 80px", position:"relative", overflow:"hidden" }}>
      <div style={{ position:"absolute", inset:0, backgroundImage:"linear-gradient(rgba(0,212,170,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(0,212,170,.04) 1px,transparent 1px)", backgroundSize:"48px 48px", WebkitMaskImage:"radial-gradient(ellipse 80% 60% at 50% 40%,black,transparent)", pointerEvents:"none" }} />
      <div style={{ position:"absolute", width:580, height:580, borderRadius:"50%", background:"rgba(0,212,170,.07)", filter:"blur(80px)", top:-100, right:-100, pointerEvents:"none" }} />
      <div style={{ position:"absolute", width:380, height:380, borderRadius:"50%", background:"rgba(59,130,246,.06)", filter:"blur(80px)", bottom:0, left:"30%", pointerEvents:"none" }} />

      <div style={{ display:"inline-flex", alignItems:"center", gap:8, background:"rgba(0,212,170,.1)", border:"1px solid rgba(0,212,170,.25)", borderRadius:100, padding:"6px 14px", width:"fit-content", fontFamily:"var(--fm)", fontSize:"0.7rem", color:"var(--teal)", letterSpacing:"0.08em", textTransform:"uppercase", marginBottom:28, animation:"fadeUp .6s ease both" }}>
        <span style={{ width:7, height:7, background:"var(--teal)", borderRadius:"50%", animation:"pulse 2s infinite" }} />
        AI-Powered Financial Forensics
      </div>

      <h1 style={{ fontFamily:"var(--fd)", fontWeight:800, fontSize:"clamp(2.8rem,6vw,5.5rem)", lineHeight:1, letterSpacing:"-0.04em", maxWidth:820, marginBottom:24, animation:"fadeUp .6s .1s ease both", animationFillMode:"both" }}>
        Detect <span style={{ color:"var(--teal)" }}>Fraud</span><br/>
        Before It <span style={{ WebkitTextStroke:"2px rgba(0,212,170,.4)", color:"transparent" }}>Hides.</span>
      </h1>

      <p style={{ fontSize:"1.06rem", color:"var(--muted)", lineHeight:1.7, maxWidth:540, marginBottom:40, fontWeight:300, animation:"fadeUp .6s .2s ease both", animationFillMode:"both" }}>
        Automated bank statement analysis that extracts, standardizes, scores risk, and generates court-ready forensic reports — in minutes, not months.
      </p>

      <div style={{ display:"flex", gap:14, animation:"fadeUp .6s .3s ease both", animationFillMode:"both" }}>
        <Btn onClick={() => setPage("upload")}>↑ Upload Statement</Btn>
        <Btn variant="ghost" onClick={() => setPage("workflow")}>View Workflow →</Btn>
      </div>

      <div style={{ display:"flex", gap:48, marginTop:72, paddingTop:40, borderTop:"1px solid var(--border)", animation:"fadeUp .6s .4s ease both", animationFillMode:"both" }}>
        {heroStats.map(({ v, l }) => (
          <div key={l} style={{ display:"flex", flexDirection:"column", gap:4 }}>
            <span style={{ fontFamily:"var(--fd)", fontSize:"2rem", fontWeight:800, color:"var(--teal)", letterSpacing:"-0.03em" }}>{v}</span>
            <span style={{ fontFamily:"var(--fm)", fontSize:"0.7rem", color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.06em" }}>{l}</span>
          </div>
        ))}
      </div>

      {/* Floating card */}
      <div style={{ position:"absolute", right:"5%", top:"50%", transform:"translateY(-50%)", width:375, background:"rgba(10,31,61,.92)", border:"1px solid var(--border)", borderRadius:16, padding:24, backdropFilter:"blur(20px)", boxShadow:"0 24px 64px rgba(0,0,0,.4),var(--glow)", animation:"float 6s ease-in-out infinite,fadeIn .8s .5s ease both", animationFillMode:"both" }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:20 }}>
          <span style={{ fontFamily:"var(--fm)", fontSize:"0.68rem", color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.08em" }}>// Live Transaction Feed</span>
          <span style={{ background:"rgba(239,68,68,.15)", border:"1px solid rgba(239,68,68,.3)", color:"#ef4444", padding:"3px 10px", borderRadius:100, fontSize:"0.67rem", fontFamily:"var(--fm)", fontWeight:500 }}>HIGH RISK</span>
        </div>
        {txns.map((t, i) => (
          <div key={i} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", padding:"9px 0", borderBottom: i < txns.length-1 ? "1px solid rgba(255,255,255,.05)" : "none" }}>
            <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
              <span style={{ fontSize:"0.84rem", fontWeight:500 }}>{t.merchant}</span>
              <span style={{ fontSize:"0.68rem", color:"var(--muted)", fontFamily:"var(--fm)" }}>{t.meta}</span>
            </div>
            <span style={{ fontFamily:"var(--fm)", fontWeight:500, fontSize:"0.86rem", color: t.dc === "debit" ? "#ef4444" : "var(--teal)" }}>{t.amount}</span>
          </div>
        ))}
        <div style={{ marginTop:18, padding:"13px 15px", background:"rgba(0,212,170,.05)", border:"1px solid rgba(0,212,170,.15)", borderRadius:10 }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline", marginBottom:8 }}>
            <span style={{ fontSize:"0.76rem", color:"var(--muted)" }}>Overall Risk Score</span>
            <span style={{ fontFamily:"var(--fd)", fontSize:"1.45rem", fontWeight:800, color:"var(--amber)" }}>62.8</span>
          </div>
          <div style={{ height:4, background:"rgba(255,255,255,.1)", borderRadius:2 }}>
            <div style={{ height:"100%", width:"62.8%", background:"linear-gradient(to right,var(--teal),var(--amber))", borderRadius:2 }} />
          </div>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────
   PAGE 2: WORKFLOW
───────────────────────────────────────────── */
const wfSteps = [
  { icon:"📤", n:1, title:"Upload", desc:"CSV, PDF, or scanned image — any format accepted" },
  { icon:"🔍", n:2, title:"Extract", desc:"OCR & parsing engine pulls all transaction fields" },
  { icon:"🧹", n:3, title:"Clean", desc:"Deduplication, missing values, standardization" },
  { icon:"📊", n:4, title:"Analyze", desc:"Trends, spending patterns, merchant & anomaly detection" },
  { icon:"🛡️", n:5, title:"Risk Score", desc:"Rule-based + AI models assign 0–100 risk score" },
  { icon:"📈", n:6, title:"Visualize", desc:"Interactive dashboards, timelines, drill-down charts" },
  { icon:"📄", n:7, title:"Report", desc:"Court-ready forensic PDF with findings & actions" },
];
const schemaFields = [
  { name:"id", type:"uuid", desc:"Unique transaction identifier" },
  { name:"debit_credit", type:"enum", desc:"DEBIT or CREDIT" },
  { name:"amount", type:"float", desc:"Transaction value in ₹" },
  { name:"balance", type:"float", desc:"Running account balance" },
  { name:"date", type:"date", desc:"Transaction date (YYYY-MM-DD)" },
  { name:"time", type:"time", desc:"HH:MM:SS timestamp" },
  { name:"transaction_type", type:"string", desc:"UPI / NEFT / CARD / ATM" },
  { name:"merchant", type:"string", desc:"Payee or merchant name" },
];
const previewRows = [
  { type:"DEBIT", amount:"₹500", date:"2023-07-26", merchant:"GAS STATION", dc:"d" },
  { type:"CREDIT", amount:"₹15,000", date:"2024-01-02", merchant:"NEFT/Salary", dc:"c" },
  { type:"DEBIT", amount:"₹3,000", date:"2023-08-22", merchant:"UPI/3234", dc:"d" },
  { type:"DEBIT", amount:"₹1,000", date:"2023-08-07", merchant:"ATM", dc:"d" },
  { type:"CREDIT", amount:"₹45,000", date:"2023-11-01", merchant:"NEFT/Transfer", dc:"c" },
];

function StepCard({ icon, n, title, desc }) {
  const [hov, setHov] = useState(false);
  return (
    <div onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)} style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", gap:13, padding:"0 10px", textAlign:"center", position:"relative", zIndex:1 }}>
      <div style={{ width:56, height:56, background: hov ? "rgba(0,212,170,.1)" : "var(--surface)", border: `1px solid ${hov ? "var(--teal)" : "var(--border)"}`, borderRadius:14, display:"flex", alignItems:"center", justifyContent:"center", fontSize:"1.2rem", position:"relative", transition:"all .3s", transform: hov ? "translateY(-4px)" : "", boxShadow: hov ? "0 0 20px rgba(0,212,170,.2)" : "none" }}>
        {icon}
        <span style={{ position:"absolute", top:-8, right:-8, width:20, height:20, background:"var(--teal)", color:"#040d1a", borderRadius:"50%", fontFamily:"var(--fm)", fontSize:"0.6rem", fontWeight:700, display:"flex", alignItems:"center", justifyContent:"center" }}>{n}</span>
      </div>
      <div style={{ fontFamily:"var(--fd)", fontWeight:700, fontSize:"0.86rem" }}>{title}</div>
      <div style={{ fontSize:"0.73rem", color:"var(--muted)", lineHeight:1.5 }}>{desc}</div>
    </div>
  );
}

function WorkflowPage() {
  return (
    <section style={{ minHeight:"100vh", padding:"120px 48px 80px", background:"var(--bg2)", borderTop:"1px solid var(--border)" }}>
      <SectionLabel>System Pipeline</SectionLabel>
      <h2 style={{ fontFamily:"var(--fd)", fontWeight:800, fontSize:"clamp(2rem,4vw,3.2rem)", letterSpacing:"-0.03em", marginBottom:16, lineHeight:1.1 }}>How It Works</h2>
      <p style={{ color:"var(--muted)", maxWidth:520, lineHeight:1.7, marginBottom:64, fontWeight:300 }}>Seven automated stages transform raw bank statements into structured, risk-scored forensic data — zero manual effort required.</p>

      <div style={{ position:"relative" }}>
        <div style={{ position:"absolute", top:28, left:28, right:28, height:1, background:"linear-gradient(to right,var(--teal),transparent)", opacity:.25, pointerEvents:"none" }} />
        <div style={{ display:"flex", gap:0 }}>
          {wfSteps.map(s => <StepCard key={s.n} {...s} />)}
        </div>
      </div>

      <div style={{ marginTop:80, display:"grid", gridTemplateColumns:"1fr 1fr", gap:40, alignItems:"start" }}>
        {/* Schema table */}
        <div style={{ background:"var(--surface)", border:"1px solid var(--border)", borderRadius:16, overflow:"hidden" }}>
          <div style={{ padding:"15px 22px", borderBottom:"1px solid var(--border)", display:"flex", alignItems:"center", gap:10, fontFamily:"var(--fm)", fontSize:"0.76rem", color:"var(--teal)" }}>
            <span style={{ width:8, height:8, background:"var(--teal)", borderRadius:"50%" }} />
            transaction_schema.json
          </div>
          <table style={{ width:"100%", borderCollapse:"collapse" }}>
            <thead><tr>
              {["Field","Type","Description"].map(h => <th key={h} style={{ padding:"9px 20px", textAlign:"left", fontFamily:"var(--fm)", fontSize:"0.64rem", color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.06em", borderBottom:"1px solid rgba(255,255,255,.05)" }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {schemaFields.map((f,i) => (
                <tr key={f.name} style={{ borderBottom: i < schemaFields.length-1 ? "1px solid rgba(255,255,255,.04)" : "none" }}>
                  <td style={{ padding:"11px 20px", fontFamily:"var(--fm)", fontSize:"0.78rem", color:"var(--teal)" }}>{f.name}</td>
                  <td style={{ padding:"11px 20px", fontFamily:"var(--fm)", fontSize:"0.78rem", color:"var(--blue)" }}>{f.type}</td>
                  <td style={{ padding:"11px 20px", fontSize:"0.74rem", color:"var(--muted)" }}>{f.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Right col */}
        <div style={{ display:"flex", flexDirection:"column", gap:20 }}>
          <SectionLabel>Sample Data Preview</SectionLabel>
          <div style={{ background:"var(--surface)", border:"1px solid var(--border)", borderRadius:16, padding:18 }}>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:8, marginBottom:6, padding:"6px 10px" }}>
              {["type","amount","date","merchant"].map(h => <span key={h} style={{ fontFamily:"var(--fm)", fontSize:"0.62rem", color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.05em" }}>{h}</span>)}
            </div>
            {previewRows.map((r,i) => {
              const [hov, setHov] = useState(false);
              return (
                <div key={i} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)} style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:8, padding:"8px 10px", marginBottom:3, background: hov ? "rgba(0,212,170,.05)" : "rgba(255,255,255,.02)", border: hov ? "1px solid var(--border)" : "1px solid transparent", borderRadius:6, transition:"all .2s" }}>
                  <span style={{ fontFamily:"var(--fm)", fontSize:"0.7rem", color: r.dc === "d" ? "#ef4444" : "var(--teal)" }}>{r.type}</span>
                  <span style={{ fontFamily:"var(--fm)", fontSize:"0.7rem" }}>{r.amount}</span>
                  <span style={{ fontFamily:"var(--fm)", fontSize:"0.7rem", color:"var(--muted)" }}>{r.date}</span>
                  <span style={{ fontFamily:"var(--fm)", fontSize:"0.7rem", color:"var(--muted)" }}>{r.merchant}</span>
                </div>
              );
            })}
          </div>
          <div style={{ padding:"16px 20px", background:"var(--surface)", border:"1px solid var(--border)", borderRadius:12 }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:"0.66rem", color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:10 }}>Auto-Detection</div>
            <p style={{ fontSize:"0.81rem", color:"var(--text)", lineHeight:1.7, fontWeight:300 }}>
              Columns matched automatically. Handles <span style={{ color:"var(--teal)" }}>valueDate</span>, <span style={{ color:"var(--teal)" }}>transactionDate</span>, <span style={{ color:"var(--teal)" }}>Debit/Credit</span>, or any bank-specific export format.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────
   PAGE 3: FEATURES
───────────────────────────────────────────── */
const features = [
  { icon:"🧠", title:"SHAP Explanations", desc:"Every flagged transaction shows exactly which factors — amount, time, merchant, frequency — drove the risk score.", tag:"Explainable AI" },
  { icon:"📉", title:"Confidence Corridors", desc:"Risk scores arrive with uncertainty bands so analysts know when to trust the model and when to step in.", tag:"Uncertainty Quantification" },
  { icon:"🧬", title:"Spending DNA Fingerprint", desc:"Builds a personalized behavioral baseline per user. Any deviation instantly triggers a targeted alert.", tag:"Anomaly Detection" },
  { icon:"🕐", title:"Circadian Rhythm Detection", desc:"Learns the hours a user never transacts and flags any activity outside their personal time window.", tag:"Behavioral AI" },
  { icon:"📡", title:"Financial Stress Index", desc:"Detects early distress signals — micro-withdrawals, cash surges, payday loan activity — before they become crises.", tag:"Predictive" },
  { icon:"📝", title:"Forensic Report Generator", desc:"LLM narrates all flagged transactions into a coherent story with a timeline, risk verdict, and action steps.", tag:"Court-Ready PDF" },
  { icon:"🔮", title:"Cash Flow Predictor", desc:"Forecasts daily balances up to 30 days ahead and warns of overdraft risk before it happens.", tag:"Forecasting" },
  { icon:"🔎", title:"Smurfing Detector", desc:"Identifies structuring patterns where large amounts are split into small transactions to evade reporting thresholds.", tag:"AML Compliance" },
  { icon:"🌐", title:"OCR Multi-Format Support", desc:"Accepts CSV, PDF, and scanned images. Auto field extraction handles any bank's export format.", tag:"Data Ingestion" },
];
const metrics = [
  { name:"Anomaly Detection Recall", val:"94.2%", w:94 },
  { name:"Smurfing Pattern Accuracy", val:"91.7%", w:91 },
  { name:"False Positive Rate", val:"4.1%", w:4 },
  { name:"OCR Field Extraction Accuracy", val:"98.3%", w:98 },
  { name:"Report Generation Speed", val:"< 45s", w:88 },
];

function FeatureCell({ icon, title, desc, tag }) {
  const [hov, setHov] = useState(false);
  return (
    <div onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)} style={{ background: hov ? "var(--surface)" : "var(--bg)", padding:"32px 28px", transition:"background .3s", cursor:"default" }}>
      <div style={{ width:48, height:48, background: hov ? "rgba(0,212,170,.1)" : "var(--surface2)", borderRadius:12, display:"flex", alignItems:"center", justifyContent:"center", fontSize:"1.15rem", marginBottom:18, transition:"all .3s" }}>{icon}</div>
      <div style={{ fontFamily:"var(--fd)", fontWeight:700, fontSize:"0.96rem", marginBottom:9 }}>{title}</div>
      <p style={{ fontSize:"0.8rem", color:"var(--muted)", lineHeight:1.6, fontWeight:300 }}>{desc}</p>
      <span style={{ display:"inline-block", marginTop:13, fontFamily:"var(--fm)", fontSize:"0.62rem", padding:"3px 10px", borderRadius:100, background:"rgba(0,212,170,.1)", color:"var(--teal)", border:"1px solid rgba(0,212,170,.2)" }}>{tag}</span>
    </div>
  );
}

function FeaturesPage() {
  const [visible, setVisible] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const obs = new IntersectionObserver(e => { if (e[0].isIntersecting) { setVisible(true); obs.disconnect(); } }, { threshold:0.3 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);

  return (
    <section style={{ minHeight:"100vh", padding:"120px 48px 80px", background:"var(--bg)" }}>
      <SectionLabel>Capabilities</SectionLabel>
      <h2 style={{ fontFamily:"var(--fd)", fontWeight:800, fontSize:"clamp(2rem,4vw,3.2rem)", letterSpacing:"-0.03em", marginBottom:16, lineHeight:1.1 }}>Intelligence Built In</h2>
      <p style={{ color:"var(--muted)", maxWidth:520, lineHeight:1.7, marginBottom:64, fontWeight:300 }}>Eight advanced AI models power every analysis — from explainable risk scoring to smurfing detection.</p>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:1, background:"var(--border)", border:"1px solid var(--border)", borderRadius:20, overflow:"hidden" }}>
        {features.map(f => <FeatureCell key={f.title} {...f} />)}
      </div>

      <div style={{ marginTop:80, display:"grid", gridTemplateColumns:"1fr 1fr", gap:48, alignItems:"center" }}>
        <div>
          <SectionLabel>Model Performance</SectionLabel>
          <h2 style={{ fontFamily:"var(--fd)", fontWeight:800, fontSize:"clamp(1.8rem,3vw,2.6rem)", letterSpacing:"-0.03em", marginBottom:14, lineHeight:1.1 }}>Smarter Risk<br/>Detection</h2>
          <p style={{ color:"var(--muted)", lineHeight:1.7, fontWeight:300, fontSize:"0.94rem" }}>Each AI component is independently validated on financial transaction datasets covering millions of records across diverse banking formats.</p>
        </div>
        <div ref={ref} style={{ display:"flex", flexDirection:"column", gap:18 }}>
          {metrics.map(m => (
            <div key={m.name} style={{ display:"flex", flexDirection:"column", gap:7 }}>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline" }}>
                <span style={{ fontSize:"0.8rem", color:"var(--muted)" }}>{m.name}</span>
                <span style={{ fontFamily:"var(--fm)", fontSize:"0.8rem", color:"var(--teal)", fontWeight:500 }}>{m.val}</span>
              </div>
              <div style={{ height:3, background:"rgba(255,255,255,.08)", borderRadius:2 }}>
                <div style={{ height:"100%", borderRadius:2, background: m.w <= 5 ? "var(--teal)" : "linear-gradient(to right,var(--teal),var(--blue))", width: visible ? `${m.w}%` : "0%", transition:"width 1s ease" }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────
   PAGE 4: UPLOAD / ANALYZE
───────────────────────────────────────────── */
const findings = [
  { color:"#ef4444", text:"Unusual ATM withdrawals at irregular hours — 12 AM to 4 AM activity window flagged" },
  { color:"#ef4444", text:"Repeated transactions to same merchant (GAS FILLING STATION, ₹500 appears 58×)" },
  { color:"var(--amber)", text:"Activity outside usual transaction time window on 23 occasions" },
  { color:"var(--amber)", text:"Structuring pattern: ₹9,800–₹10,200 range (23 transactions, total ₹2,27,800)" },
  { color:"var(--teal)", text:"Cash flow forecast: High overdraft risk expected on Jun 26" },
];
const colFields = ["id","debit_credit","amount","balance","date","time","transaction_type","merchant"];

function UploadPage() {
  const [dragging, setDragging] = useState(false);
  const [uploaded, setUploaded] = useState(false);

  const trigger = () => { setUploaded(true); setTimeout(() => setUploaded(false), 3000); };

  return (
    <section style={{ minHeight:"100vh", padding:"120px 48px 80px", background:"var(--bg2)", borderTop:"1px solid var(--border)" }}>
      <SectionLabel>Analyze Now</SectionLabel>
      <h2 style={{ fontFamily:"var(--fd)", fontWeight:800, fontSize:"clamp(2rem,4vw,3.2rem)", letterSpacing:"-0.03em", marginBottom:16, lineHeight:1.1 }}>Upload & Get Results</h2>
      <p style={{ color:"var(--muted)", maxWidth:540, lineHeight:1.7, marginBottom:64, fontWeight:300 }}>Drop a statement and receive a complete forensic analysis — risk score, flagged transactions, and an evidence-ready PDF — within seconds.</p>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:48, alignItems:"start" }}>
        {/* Left */}
        <div style={{ display:"flex", flexDirection:"column", gap:18 }}>
          <div
            onDragEnter={e => { e.preventDefault(); setDragging(true); }}
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={e => { e.preventDefault(); setDragging(false); trigger(); }}
            style={{ border:`2px dashed ${dragging ? "var(--teal)" : "rgba(0,212,170,.25)"}`, borderRadius:20, padding:"48px 32px", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", textAlign:"center", gap:14, background: dragging ? "rgba(0,212,170,.06)" : uploaded ? "rgba(0,212,170,.04)" : "rgba(0,212,170,.02)", transition:"all .3s", cursor:"pointer", boxShadow: dragging ? "0 0 32px rgba(0,212,170,.12)" : "none" }}
          >
            <div style={{ fontSize:"2.8rem" }}>{uploaded ? "✅" : "📂"}</div>
            <div style={{ fontFamily:"var(--fd)", fontWeight:700, fontSize:"1.12rem" }}>{uploaded ? "File Received!" : "Drop Your Bank Statement"}</div>
            <div style={{ fontSize:"0.8rem", color:"var(--muted)", lineHeight:1.6 }}>
              {uploaded ? "Analysis running — results will appear shortly." : "Drag & drop your file, or click Browse. Columns are auto-detected."}
            </div>
            <div style={{ display:"flex", gap:8, flexWrap:"wrap", justifyContent:"center" }}>
              {["CSV","PDF","PNG / JPG"].map(f => <span key={f} style={{ background:"var(--surface)", border:"1px solid var(--border)", borderRadius:6, padding:"4px 11px", fontFamily:"var(--fm)", fontSize:"0.68rem", color:"var(--muted)" }}>{f}</span>)}
            </div>
            <Btn onClick={trigger} style={{ marginTop:6 }}>Browse Files</Btn>
          </div>

          <div style={{ padding:"18px 20px", background:"var(--surface)", border:"1px solid var(--border)", borderRadius:14 }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:"0.66rem", color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:12 }}>Expected CSV Columns</div>
            <div style={{ display:"flex", flexWrap:"wrap", gap:8 }}>
              {colFields.map(f => <span key={f} style={{ background:"rgba(0,212,170,.06)", border:"1px solid rgba(0,212,170,.2)", borderRadius:6, padding:"4px 11px", fontFamily:"var(--fm)", fontSize:"0.7rem", color:"var(--teal)" }}>{f}</span>)}
            </div>
            <p style={{ marginTop:12, fontSize:"0.76rem", color:"var(--muted)", lineHeight:1.6 }}>Any variation in column naming is handled automatically. Max file size: <span style={{ color:"var(--text)" }}>200 MB</span>.</p>
          </div>
        </div>

        {/* Right */}
        <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
          <div style={{ fontFamily:"var(--fm)", fontSize:"0.68rem", color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.08em" }}>// Sample Analysis Output</div>

          {/* Risk score */}
          <div style={{ background:"var(--surface)", border:"1px solid var(--border)", borderRadius:16, padding:22 }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:"0.68rem", color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:16 }}>Overall Risk Score</div>
            <div style={{ display:"flex", alignItems:"baseline", gap:6, marginBottom:13 }}>
              <span style={{ fontFamily:"var(--fd)", fontSize:"3.4rem", fontWeight:800, lineHeight:1, color:"var(--amber)" }}>62.8</span>
              <span style={{ fontFamily:"var(--fm)", fontSize:"1.1rem", color:"var(--muted)" }}>/ 100</span>
            </div>
            <span style={{ display:"inline-flex", alignItems:"center", gap:6, background:"rgba(239,68,68,.12)", border:"1px solid rgba(239,68,68,.25)", color:"#ef4444", padding:"4px 13px", borderRadius:6, fontFamily:"var(--fm)", fontSize:"0.68rem", fontWeight:600, textTransform:"uppercase", letterSpacing:"0.05em" }}>⚠ High Risk</span>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", padding:"11px 14px", marginTop:14, background:"rgba(239,68,68,.05)", border:"1px solid rgba(239,68,68,.15)", borderRadius:8, fontSize:"0.8rem" }}>
              <span style={{ color:"var(--muted)" }}>Flagged Transactions</span>
              <span style={{ fontFamily:"var(--fm)", color:"#ef4444", fontWeight:600 }}>868 / 985</span>
            </div>
          </div>

          {/* Findings */}
          <div style={{ background:"var(--surface)", border:"1px solid var(--border)", borderRadius:16, padding:22 }}>
            <div style={{ fontFamily:"var(--fm)", fontSize:"0.68rem", color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:16 }}>Key Findings</div>
            <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
              {findings.map((f,i) => (
                <div key={i} style={{ display:"flex", alignItems:"flex-start", gap:11, fontSize:"0.8rem", color:"var(--muted)", lineHeight:1.55 }}>
                  <div style={{ width:6, height:6, borderRadius:"50%", background:f.color, marginTop:6, flexShrink:0 }} />
                  {f.text}
                </div>
              ))}
            </div>
          </div>

          {/* PDF button */}
          <button
            onClick={() => alert("PDF generation — connect to backend API")}
            style={{ width:"100%", background:"linear-gradient(135deg,rgba(0,212,170,.1),rgba(59,130,246,.1))", border:"1px solid rgba(0,212,170,.3)", color:"var(--teal)", padding:17, borderRadius:12, fontFamily:"var(--fd)", fontWeight:700, fontSize:"0.93rem", cursor:"pointer", transition:"all .3s", display:"flex", alignItems:"center", justifyContent:"center", gap:10, letterSpacing:"-0.01em" }}
            onMouseEnter={e => { e.currentTarget.style.boxShadow = "0 0 24px rgba(0,212,170,.2)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
            onMouseLeave={e => { e.currentTarget.style.boxShadow = "none"; e.currentTarget.style.transform = ""; }}
          >📄 Generate Forensic Evidence PDF</button>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────
   FOOTER
───────────────────────────────────────────── */
function Footer({ setPage }) {
  const links = [["Overview","hero"],["Workflow","workflow"],["Features","features"],["Analyze","upload"]];
  return (
    <footer style={{ padding:"40px 48px", borderTop:"1px solid var(--border)", display:"flex", justifyContent:"space-between", alignItems:"center", background:"var(--bg)" }}>
      <div>
        <div style={{ fontFamily:"var(--fd)", fontWeight:800, fontSize:"1.2rem", letterSpacing:"-0.03em", display:"flex", alignItems:"center", gap:9, marginBottom:7 }}>
          <div style={{ width:28, height:28, background:"linear-gradient(135deg,var(--teal),#0066ff)", borderRadius:7, display:"flex", alignItems:"center", justifyContent:"center", fontFamily:"var(--fm)", fontSize:"0.68rem", fontWeight:700, color:"#040d1a" }}>BF</div>
          BankForensiq
        </div>
        <div style={{ fontFamily:"var(--fm)", fontSize:"0.72rem", color:"var(--muted)" }}>© 2026 · Jeevan M · Nidhi Mallikarjuna · Hemanth · PES University</div>
      </div>
      <div style={{ display:"flex", gap:24, alignItems:"center" }}>
        {links.map(([label,p]) => (
          <button key={p} onClick={() => setPage(p)} style={{ background:"none", border:"none", cursor:"pointer", fontFamily:"var(--fb)", fontSize:"0.8rem", color:"var(--muted)", transition:"color .2s" }}
            onMouseEnter={e => e.currentTarget.style.color = "var(--teal)"}
            onMouseLeave={e => e.currentTarget.style.color = "var(--muted)"}
          >{label}</button>
        ))}
        <a href="https://github.com/ItsjeevanM/Automated-Banking-Fraudent-behavior-" target="_blank" rel="noreferrer" style={{ fontFamily:"var(--fb)", fontSize:"0.8rem", color:"var(--muted)", textDecoration:"none" }}
          onMouseEnter={e => e.currentTarget.style.color = "var(--teal)"}
          onMouseLeave={e => e.currentTarget.style.color = "var(--muted)"}
        >GitHub ↗</a>
      </div>
    </footer>
  );
}

/* ─────────────────────────────────────────────
   ROOT APP
───────────────────────────────────────────── */
const PAGES = ["hero","workflow","features","upload"];

export default function App() {
  const [page, setPage] = useState("hero");
  const [transitioning, setTransitioning] = useState(false);
  const [display, setDisplay] = useState("hero");

  useEffect(() => {
    const el = document.createElement("style");
    el.textContent = CSS;
    document.head.appendChild(el);
    return () => el.remove();
  }, []);

  const navigate = (to) => {
    if (to === page || transitioning) return;
    setTransitioning(true);
    setTimeout(() => {
      setDisplay(to);
      setPage(to);
      setTransitioning(false);
    }, 200);
  };

  useEffect(() => {
    const handle = (e) => {
      const i = PAGES.indexOf(page);
      if (e.key === "ArrowRight" && i < PAGES.length - 1) navigate(PAGES[i + 1]);
      if (e.key === "ArrowLeft"  && i > 0)                navigate(PAGES[i - 1]);
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [page, transitioning]);

  const renderPage = () => {
    const props = { setPage: navigate };
    switch (display) {
      case "hero":     return <HeroPage {...props} />;
      case "workflow": return <WorkflowPage {...props} />;
      case "features": return <FeaturesPage {...props} />;
      case "upload":   return <UploadPage {...props} />;
    }
  };

  return (
    <div id="page-scroll" style={{ minHeight:"100vh", display:"flex", flexDirection:"column", overflowY:"auto" }}>
      <Nav page={page} setPage={navigate} />

      <div key={display} style={{ flex:1, opacity: transitioning ? 0 : 1, transform: transitioning ? "translateY(10px)" : "translateY(0)", transition:"opacity .2s ease, transform .2s ease" }}>
        {renderPage()}
      </div>

      <Footer setPage={navigate} />

      {/* Page dots */}
      <div style={{ position:"fixed", bottom:24, left:"50%", transform:"translateX(-50%)", display:"flex", gap:7, alignItems:"center", zIndex:50, background:"rgba(4,13,26,.85)", backdropFilter:"blur(10px)", border:"1px solid var(--border)", borderRadius:100, padding:"7px 14px" }}>
        {PAGES.map(p => (
          <button key={p} onClick={() => navigate(p)} title={p} style={{ width: page === p ? 22 : 7, height:7, background: page === p ? "var(--teal)" : "rgba(107,130,168,.4)", border:"none", borderRadius:100, cursor:"pointer", transition:"all .3s", padding:0 }} />
        ))}
      </div>

      {/* Page counter */}
      <div style={{ position:"fixed", bottom:24, right:24, fontFamily:"var(--fm)", fontSize:"0.66rem", color:"var(--muted)", background:"rgba(4,13,26,.85)", backdropFilter:"blur(10px)", border:"1px solid var(--border)", borderRadius:6, padding:"5px 11px", zIndex:50, letterSpacing:"0.06em", textTransform:"uppercase" }}>
        {PAGES.indexOf(page)+1} / {PAGES.length} — {page}
      </div>
    </div>
  );
}
