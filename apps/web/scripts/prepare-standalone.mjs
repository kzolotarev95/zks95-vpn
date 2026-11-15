import { cpSync, mkdirSync } from "node:fs";
import { join } from "node:path";

// Next.js leaves static assets outside standalone; include them for `npm start`.
const target = join(".next", "standalone", ".next", "static");
mkdirSync(target, { recursive: true });
cpSync(join(".next", "static"), target, { recursive: true });
