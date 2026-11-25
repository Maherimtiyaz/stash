export type Progress = "try" | "done" | "skip";

export interface Save {
  id: number;
  kind: "reel" | "post" | "link";
  url: string;
  caption: string;
  creator: string;
  category: string;
  tags: string[];
  progress: Progress;
  note: string;
  board_id: number | null;
  board_name: string | null;
  plan_day: string | null; // YYYY-MM-DD
  remind_at: string | null; // ISO datetime
  saved_at: string;
  processing: "queued" | "done" | "failed";
}

export interface Board {
  id: number;
  name: string;
  count: number;
}

export interface Shelf {
  name: string;
  count: number;
  todo: number;
}

export interface Me {
  id: number;
  name: string;
  instagram_linked: boolean;
  email: string;
}

export interface ReminderSettings {
  channels: {
    dm: { open: boolean; until: string | null };
    push: { devices: number; public_key: string; live: boolean };
    email: { address: string; live: boolean };
  };
  upcoming: { id: number; caption: string; category: string; remind_at: string }[];
}

export interface Home {
  recent: Save[];
  on_this_day: Save[];
  counts: { total: number; todo: number; done: number };
}

export interface Week {
  start: string;
  today: string;
  days: { date: string; saves: Save[] }[];
  pile: Save[];
}

export type SaveChanges = Partial<Pick<Save, "progress" | "note" | "board_id" | "plan_day" | "remind_at" | "category">>;
export type ReviewAction = "keep" | "let_go" | "later";

export interface ImportSummary {
  id: number;
  found: number;
  added: number;
  duplicates: number;
  put_on_piles: number;
  piles_created: string[];
  shelves: Record<string, number>;
}

export interface ImportRecord {
  id: number;
  file_name: string;
  created_at: string;
  found: number;
  added: number;
  duplicates: number;
  undone_at: string | null;
}
