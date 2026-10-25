import React from "react";

/**
 * Always-visible variant of SkillHint: the ready command (skill name plus the document id) is printed in the page
 * with a one-click copy button, for places where the user will most likely run the skill right away.
 */
const SkillCommand = ({ command, children }: { command: string; children?: React.ReactNode }) => {
  const [copied, setCopied] = React.useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard may be unavailable (insecure origin); the command stays selectable on the page
    }
  };

  return (
    <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginLeft: 6 }}>
      <span>Skorzystaj ze skilla:</span>
      <code style={{ userSelect: "all", wordBreak: "break-all" }}>{command}</code>
      <button type="button" className="button" onClick={copy}>{copied ? "Skopiowano" : "Kopiuj"}</button>
      {children && <small style={{ flexBasis: "100%", color: "#667" }}>{children}</small>}
    </span>
  );
};

export default SkillCommand;
