import { useState, useEffect } from "react";

export default function Nav({ currentPage, setPage }) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const links = [
    { label: "Overview", page: "hero" },
    { label: "Workflow", page: "workflow" },
    { label: "Features", page: "features" },
    { label: "Analyze", page: "upload" },
  ];

  return (
    <nav style={{
      position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "18px 48px",
      background: scrolled ? "rgba(4,13,26,0.97)" : "linear-gradient(to bottom, rgba(4,13,26,0.95), transparent)",
      backdropFilter: "blur(14px)",
      borderBottom: scrolled ? "1px solid var(--border)" : "1px solid transparent",
      transition: "all 0.3s",
    }}>
      {/* Logo */}
      <div
        onClick={() => setPage("hero")}
        style={{
          fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "1.3rem",
          letterSpacing: "-0.03em", color: "var(--text)",
          display: "flex", alignItems: "center", gap: 10, cursor: "pointer",
        }}
      >
        <div style={{
          width: 32, height: 32,
          background: "linear-gradient(135deg, var(--teal), #0066ff)",
          borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: "var(--font-mono)", fontSize: "0.8rem", fontWeight: 700, color: "#040d1a",
        }}>BF</div>
        BankForensiq
      </div>

      {/* Links */}
      <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
        {links.map(({ label, page }) => (
          <button
            key={page}
            onClick={() => setPage(page)}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontFamily: "var(--font-body)", fontSize: "0.88rem", fontWeight: 500,
              color: currentPage === page ? "var(--teal)" : "var(--muted)",
              transition: "color 0.2s", letterSpacing: "0.02em",
            }}
          >{label}</button>
        ))}
        <button
          onClick={() => setPage("upload")}
          style={{
            background: "var(--teal)", color: "#040d1a",
            padding: "9px 22px", borderRadius: 7,
            border: "none", cursor: "pointer",
            fontFamily: "var(--font-body)", fontWeight: 600, fontSize: "0.88rem",
            transition: "all 0.2s",
          }}
          onMouseEnter={e => { e.target.style.background = "var(--teal2)"; e.target.style.transform = "translateY(-1px)"; }}
          onMouseLeave={e => { e.target.style.background = "var(--teal)"; e.target.style.transform = ""; }}
        >Upload Statement</button>
      </div>
    </nav>
  );
}
