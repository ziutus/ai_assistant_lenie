import React from "react";

/** True when the viewport is at least `breakpoint` px wide. Used to gate
 *  desktop-only UI (e.g. the country map in the reader view) so it never
 *  loads its assets (tiles, GeoJSON) on narrow/mobile screens. */
export function useIsDesktop(breakpoint = 1024): boolean {
  const query = `(min-width: ${breakpoint}px)`;
  const [isDesktop, setIsDesktop] = React.useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches
  );

  React.useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setIsDesktop(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return isDesktop;
}
