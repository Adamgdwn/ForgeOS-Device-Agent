import type { Activity } from "./api.ts";

/** Keep account failures for the reading pass even when its snackbar disappears. */
export function outlookWarnings(events: Activity[]): string[] {
  const last = events.findLastIndex(
    (e) => e.type === "notice" && Array.isArray(e.data.warnings),
  );
  if (last < 0) return [];
  const start = events.slice(0, last).findLastIndex((e) => e.type === "user");
  const accountWarnings = events
    .slice(start + 1, last + 1)
    .flatMap((e) =>
      e.type === "notice" && Array.isArray(e.data.warnings)
        ? e.data.warnings.filter((text: string) =>
            /sign in|offline|not connected|couldn.t sync|unable to sync/i.test(
              text,
            ),
          )
        : [],
    );
  return [
    ...new Set<string>([...accountWarnings, ...events[last].data.warnings]),
  ];
}
