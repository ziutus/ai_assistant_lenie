import React from "react";
import InfoTip from "./InfoTip";

/** ⓘ hint telling the user that a Claude Code / Codex skill can do the task, with a copyable command. */
const SkillHint = ({ skill, command, children }: { skill: string; command: string; children: React.ReactNode }) => {
  const [copied, setCopied] = React.useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard may be unavailable (insecure origin); the command stays visible for manual copy
    }
  };

  return (
    <InfoTip label={`Skill ${skill}`}>
      <div>{children}</div>
      <div style={{ marginTop: 6 }}>
        <code style={{ userSelect: "all", wordBreak: "break-all" }}>{command}</code>
      </div>
      <button type="button" className="button" style={{ marginTop: 6 }} onClick={copy}>
        {copied ? "Skopiowano" : "Kopiuj komendę"}
      </button>
      <div style={{ marginTop: 6, color: "#667", fontSize: "0.9em" }}>
        Wklej w sesji Claude Code (skill {skill}).
      </div>
    </InfoTip>
  );
};

export default SkillHint;
