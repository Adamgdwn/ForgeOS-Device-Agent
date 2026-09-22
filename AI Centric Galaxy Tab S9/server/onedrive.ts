import {
  PublicClientApplication,
  type DeviceCodeRequest,
} from "@azure/msal-node";
import {
  createCipheriv,
  createDecipheriv,
  randomBytes,
  randomUUID,
} from "node:crypto";
import { existsSync, readFileSync, mkdirSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import {
  STATE,
  privateWrite,
  readSettings,
  setExistingMicrosoft,
} from "./config.ts";
import { ExistingMicrosoftClient } from "./existing-microsoft.ts";
import { digest, readDocument, safePath, visible } from "./files.ts";
import {
  documentByteLimit,
  MAX_BATCH_BYTES,
  DOCUMENT_LIMIT_MESSAGE,
} from "../shared/document-limits.ts";
import {
  newStage,
  installMaterials,
  extractMaterial,
  type MaterialTarget,
  type Source,
} from "./materials.ts";
import type { Store } from "./store.ts";

type Account = {
  slot: number;
  label: string;
  homeId: string | null;
  username: string | null;
  status: string;
  source?: "host";
  readOnly?: boolean;
};
type CloudItem = {
  id: string;
  name: string;
  size: number;
  eTag: string;
  webUrl: string;
  folder?: { childCount: number };
  parentReference?: { driveId: string };
};
const scopes = ["User.Read", "Files.ReadWrite"];
const graph = "https://graph.microsoft.com/v1.0";
function cloudUrl(raw: string) {
  const url = new URL(raw);
  if (
    url.protocol !== "https:" ||
    (url.port !== "" && url.port !== "443") ||
    url.username ||
    url.password ||
    (url.hostname !== "my.microsoftpersonalcontent.com" &&
      ![
        "sharepoint.com",
        "1drv.com",
        "onedrive.com",
        "storage.live.com",
        "onedrive.live.com",
      ].some(
        (domain) =>
          url.hostname === domain || url.hostname.endsWith(`.${domain}`),
      ))
  )
    throw new Error("Microsoft returned an unsupported file transfer host.");
  return url.toString();
}
async function bytes(response: Response, limit: number): Promise<Buffer> {
  if (!response.ok)
    throw new Error(`File transfer failed (${response.status}).`);
  const chunks: Buffer[] = [];
  let size = 0;
  if (!response.body) throw new Error("File transfer returned no content.");
  for await (const part of response.body) {
    size += part.length;
    if (size > limit) {
      throw new Error("File exceeds the pilot import limit.");
    }
    chunks.push(Buffer.from(part));
  }
  return Buffer.concat(chunks);
}
export class OneDrive {
  store: Store;
  clients = new Map<number, PublicClientApplication>();
  pending = new Map<
    number,
    {
      code?: string;
      url?: string;
      expires?: number;
      request: DeviceCodeRequest;
    }
  >();
  errors = new Map<number, string>();
  cursors = new Map<string, { slot: number; url: string }>();
  key: Buffer;
  fetcher: typeof fetch;
  existing: ExistingMicrosoftClient;
  constructor(store: Store, fetcher: typeof fetch = fetch) {
    this.store = store;
    this.fetcher = fetcher;
    this.existing = new ExistingMicrosoftClient(fetcher);
    const keyPath = resolve(STATE, "token-cache.key");
    if (!existsSync(keyPath)) privateWrite(keyPath, randomBytes(32));
    this.key = readFileSync(keyPath);
  }
  accounts() {
    const accounts = this.store.db
      .prepare(
        "SELECT * FROM accounts WHERE status <> 'removed' ORDER BY slot",
      )
      .all() as unknown as Account[];
    if (readSettings().existingMicrosoft) accounts.push(this.account(4));
    return accounts.map(({ homeId, ...a }) => ({
      ...a,
      connectionId: homeId ? digest(homeId) : "",
      error: this.errors.get(a.slot),
      login: this.pending.get(a.slot)
        ? {
            code: this.pending.get(a.slot)?.code,
            url: this.pending.get(a.slot)?.url,
            expires: this.pending.get(a.slot)?.expires,
          }
        : undefined,
    }));
  }
  account(slot: number): Account {
    if (slot === 4) {
      const connection = readSettings().existingMicrosoft;
      if (!connection)
        throw new Error(
          "This host Microsoft connection has been disconnected.",
        );
      return {
        slot,
        label: connection.label,
        username: connection.username,
        homeId: `m365:${connection.driveId}:${connection.userId}`,
        status: "connected",
        source: "host",
        readOnly: true,
      };
    }
    const a = this.store.db
      .prepare("SELECT * FROM accounts WHERE slot=?")
      .get(slot) as Account | undefined;
    if (!a || a.status === "removed")
      throw new Error("Add this OneDrive connection again before using it.");
    return a;
  }
  add() {
    const available = this.store.db
      .prepare(
        "SELECT slot FROM accounts WHERE status='removed' ORDER BY slot LIMIT 1",
      )
      .get() as { slot: number } | undefined;
    if (!available)
      throw new Error(
        "All three OneDrive connections are in use. Remove one before adding another.",
      );
    this.store.db
      .prepare(
        "UPDATE accounts SET label=?, status='disconnected' WHERE slot=?",
      )
      .run(`OneDrive ${available.slot}`, available.slot);
    return { slot: available.slot };
  }
  client(slot: number) {
    const existing = this.clients.get(slot);
    if (existing) return existing;
    const clientId = readSettings().microsoftClientId;
    if (!clientId)
      throw new Error(
        "Microsoft sign-in is not ready yet. The person setting up Galaxy Workspace needs to enable it on the host computer.",
      );
    const path = resolve(STATE, `onedrive-${slot}.cache`);
    const app: PublicClientApplication = new PublicClientApplication({
      auth: {
        clientId,
        authority: "https://login.microsoftonline.com/common",
      },
      system: {
        loggerOptions: { piiLoggingEnabled: false, loggerCallback: () => {} },
      },
      cache: {
        cachePlugin: {
          beforeCacheAccess: async (context) => {
            if (this.clients.get(slot) !== app)
              throw new Error("This OneDrive connection was removed.");
            if (existsSync(path)) {
              const packed = readFileSync(path),
                decipher = createDecipheriv(
                  "aes-256-gcm",
                  this.key,
                  packed.subarray(0, 12),
                );
              decipher.setAuthTag(packed.subarray(12, 28));
              context.tokenCache.deserialize(
                Buffer.concat([
                  decipher.update(packed.subarray(28)),
                  decipher.final(),
                ]).toString("utf8"),
              );
            }
          },
          afterCacheAccess: async (context) => {
            // An in-flight Microsoft response must not recreate a removed cache.
            if (this.clients.get(slot) === app && context.cacheHasChanged) {
              const iv = randomBytes(12),
                cipher = createCipheriv("aes-256-gcm", this.key, iv);
              const encrypted = Buffer.concat([
                cipher.update(context.tokenCache.serialize(), "utf8"),
                cipher.final(),
              ]);
              privateWrite(
                path,
                Buffer.concat([iv, cipher.getAuthTag(), encrypted]),
              );
            }
          },
        },
      },
    });
    this.clients.set(slot, app);
    return app;
  }
  async connect(slot: number, label: string) {
    if (slot === 4)
      throw new Error(
        "Link the existing Microsoft connection from the host terminal.",
      );
    this.account(slot);
    if (this.pending.has(slot))
      throw new Error("Sign-in is already waiting for this connection.");
    const app = this.client(slot);
    this.errors.delete(slot);
    const request: DeviceCodeRequest = {
      scopes,
      timeout: 300,
      deviceCodeCallback: (response) => {
        const entry = this.pending.get(slot);
        if (entry?.request === request && !request.cancel)
          Object.assign(entry, {
            code: response.userCode,
            url: response.verificationUri,
            expires: Date.now() + response.expiresIn * 1000,
          });
      },
    };
    this.pending.set(slot, { request });
    this.store.db
      .prepare(
        "UPDATE accounts SET label=?, status='connecting' WHERE slot=?",
      )
      .run(label.trim().slice(0, 60) || `OneDrive ${slot}`, slot);
    void app
      .acquireTokenByDeviceCode(request)
      .then(async (result) => {
        if (this.pending.get(slot)?.request !== request || request.cancel)
          return;
        if (!result?.account)
          throw new Error("Microsoft did not return an account.");
        const duplicate = this.store.db
          .prepare("SELECT slot FROM accounts WHERE homeId=? AND slot<>?")
          .get(result.account.homeAccountId, slot);
        if (duplicate)
          throw new Error(
            "That Microsoft account is already connected in another slot. Choose a different account.",
          );
        this.store.db
          .prepare(
            "UPDATE accounts SET homeId=?, username=?, status='connected' WHERE slot=?",
          )
          .run(result.account.homeAccountId, result.account.username, slot);
      })
      .catch((error) => {
        if (this.pending.get(slot)?.request !== request || request.cancel)
          return;
        const code = typeof error.errorCode === "string" ? error.errorCode : "";
        this.errors.set(
          slot,
          code
            ? `Microsoft sign-in did not complete (${code}). Your organization may require administrator approval.`
            : error.message ===
                "That Microsoft account is already connected in another slot. Choose a different account."
              ? error.message
              : "Microsoft sign-in did not complete. Try again.",
        );
        const current = this.account(slot);
        this.store.db
          .prepare("UPDATE accounts SET status=? WHERE slot=?")
          .run(current.homeId ? "connected" : "disconnected", slot);
      })
      .finally(() => {
        if (this.pending.get(slot)?.request === request)
          this.pending.delete(slot);
      });
    return { started: true };
  }
  async disconnect(slot: number, remove = false) {
    if (slot === 4) {
      setExistingMicrosoft();
      this.errors.delete(slot);
      for (const [id, cursor] of this.cursors)
        if (cursor.slot === slot) this.cursors.delete(id);
      return;
    }
    this.account(slot);
    const pending = this.pending.get(slot);
    if (pending) pending.request.cancel = true;
    this.pending.delete(slot);
    this.clients.delete(slot);
    rmSync(resolve(STATE, `onedrive-${slot}.cache`), { force: true });
    this.store.db
      .prepare(
        "UPDATE accounts SET homeId=NULL, username=NULL, status=? WHERE slot=?",
      )
      .run(remove ? "removed" : "disconnected", slot);
    this.errors.delete(slot);
    for (const [id, cursor] of this.cursors)
      if (cursor.slot === slot) this.cursors.delete(id);
  }
  async remove(slot: number) {
    await this.disconnect(slot, true);
  }
  async token(slot: number) {
    if (slot === 4) {
      const connection = readSettings().existingMicrosoft;
      if (!connection)
        throw new Error(
          "Reconnect the existing Microsoft account from this host.",
        );
      const token = await this.existing.token(connection);
      if (
        JSON.stringify(connection) !==
        JSON.stringify(readSettings().existingMicrosoft)
      )
        throw new Error(
          "The host connection changed during this request. Try again.",
        );
      return token;
    }
    const a = this.account(slot);
    if (!a.homeId) throw new Error("Connect this OneDrive account first.");
    const app = this.client(slot),
      account = await app.getTokenCache().getAccountByHomeId(a.homeId);
    if (!account)
      throw new Error("This OneDrive connection needs a new sign-in.");
    try {
      const result = await app.acquireTokenSilent({ account, scopes });
      if (this.clients.get(slot) !== app)
        throw new Error("Connection changed.");
      if (!result?.accessToken) throw new Error("Missing access token.");
      return result.accessToken;
    } catch {
      throw new Error("This OneDrive connection needs a new sign-in.");
    }
  }
  async request(slot: number, path: string, init: RequestInit = {}) {
    const hostIdentity = this.account(slot).homeId;
    let url = path.startsWith(graph + "/") ? path : graph + path;
    if (!url.startsWith(graph + "/"))
      throw new Error("Invalid Microsoft Graph address.");
    if (slot === 4) {
      if ((init.method || "GET").toUpperCase() !== "GET")
        throw new Error(
          "This host connection supports browsing and importing only. Keep edits in the local draft.",
        );
      const connection = readSettings().existingMicrosoft;
      if (!connection)
        throw new Error(
          "Reconnect the existing Microsoft account from this host.",
        );
      const parsed = new URL(url);
      const drivePath = `/v1.0/drives/${encodeURIComponent(connection.driveId)}/`;
      if (parsed.pathname.startsWith("/v1.0/me/drive/"))
        parsed.pathname =
          drivePath + parsed.pathname.slice("/v1.0/me/drive/".length);
      if (!parsed.pathname.startsWith(drivePath))
        throw new Error(
          "This request does not belong to the linked OneDrive.",
        );
      url = parsed.toString();
    }
    const token = await this.token(slot);
    if (this.account(slot).homeId !== hostIdentity)
      throw new Error(
        "The host connection changed during this request. Try again.",
      );
    const response = await this.fetcher(url, {
      ...init,
      redirect: "manual",
      signal: AbortSignal.timeout(30_000),
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
    if (!response.ok && response.status !== 302) {
      if (response.status === 412)
        throw new Error(
          "The OneDrive original changed. Your draft is preserved; import the current version before saving.",
        );
      if (response.status === 429)
        throw new Error(
          "OneDrive is busy. Wait a moment and retry this action.",
        );
      throw new Error(
        `OneDrive request failed (${response.status}). Check this account’s access and sign-in.`,
      );
    }
    return response;
  }
  async browse(slot: number, itemId = "root", cursor?: string) {
    this.account(slot);
    let path = `/me/drive/${
      itemId === "root" ? "root" : `items/${encodeURIComponent(itemId)}`
    }/children?$top=100&$select=id,name,size,folder,eTag,webUrl,parentReference`;
    if (cursor) {
      const known = this.cursors.get(cursor);
      if (!known || known.slot !== slot)
        throw new Error("Folder page expired. Open the folder again.");
      path = known.url;
    }
    const data = (await (await this.request(slot, path)).json()) as {
      value: CloudItem[];
      "@odata.nextLink"?: string;
    };
    let nextCursor: string | undefined;
    if (data["@odata.nextLink"]) {
      const next = data["@odata.nextLink"];
      if (!next.startsWith(graph + "/"))
        throw new Error("Invalid OneDrive continuation address.");
      nextCursor = randomUUID();
      if (this.cursors.size > 1000) this.cursors.clear();
      this.cursors.set(nextCursor, { slot, url: next });
    }
    return {
      items: data.value.map((i) => ({
        id: i.id,
        name: i.name,
        size: i.size,
        directory: !!i.folder,
        webUrl: i.webUrl,
      })),
      nextCursor,
    };
  }
  async content(slot: number, item: CloudItem) {
    const homeId = this.account(slot).homeId;
    if (!homeId)
      throw new Error(
        "Reconnect this OneDrive account before opening files.",
      );
    if (item.folder || !visible(item.name))
      throw new Error("Choose a visible document to open.");
    if (
      !Number.isSafeInteger(item.size) ||
      item.size < 0 ||
      item.size > documentByteLimit(item.name)
    )
      throw new Error(DOCUMENT_LIMIT_MESSAGE);
    const response = await this.request(
      slot,
      `/me/drive/items/${encodeURIComponent(item.id)}/content`,
    );
    // Graph supplies a short-lived URL. Never forward its bearer to a transfer host.
    const data =
      response.status === 302
        ? await bytes(
            await this.fetcher(
              cloudUrl(response.headers.get("location") || ""),
              {
                signal: AbortSignal.timeout(30_000),
                redirect: "error",
              },
            ),
            documentByteLimit(item.name),
          )
        : await bytes(response, documentByteLimit(item.name));
    const latest: CloudItem = await (
      await this.request(
        slot,
        `/me/drive/items/${encodeURIComponent(item.id)}`,
      )
    ).json();
    if (this.account(slot).homeId !== homeId)
      throw new Error(
        "The account connection changed while opening this file. Try again.",
      );
    if (!item.eTag || latest.eTag !== item.eTag)
      throw new Error(`${item.name} changed while opening. Open it again.`);
    return data;
  }
  async preview(slot: number, itemId: string, connectionId: string) {
    const homeId = this.account(slot).homeId;
    if (!homeId || digest(homeId) !== connectionId)
      throw new Error(
        "The selected account changed. Browse and select the file again.",
      );
    const item: CloudItem = await (
      await this.request(
        slot,
        `/me/drive/items/${encodeURIComponent(itemId)}`,
      )
    ).json();
    if (this.account(slot).homeId !== homeId)
      throw new Error(
        "The selected account changed. Browse and select the file again.",
      );
    const data = await this.content(slot, item);
    const stage = newStage();
    try {
      privateWrite(safePath(stage, item.name), data);
      const document = await readDocument(stage, item.name);
      if (this.account(slot).homeId !== homeId)
        throw new Error(
          "The selected account changed. Browse and select the file again.",
        );
      return {
        ...document,
        source: {
          originalName: item.name,
          webUrl: item.webUrl,
          label: this.account(slot).label,
        },
      };
    } finally {
      rmSync(stage, { recursive: true, force: true });
    }
  }
  async collect(
    name: string,
    selected: { slot: number; itemId: string; connectionId?: string }[],
    target?: MaterialTarget,
  ) {
    if (!selected.length || selected.length > 50)
      throw new Error("Select between 1 and 50 files or folders.");
    const identities = new Map(
      selected.map((item) => [item.slot, this.account(item.slot).homeId]),
    );
    for (const item of selected)
      if (
        item.connectionId &&
        digest(identities.get(item.slot) || "") !== item.connectionId
      )
        throw new Error(
          "A selected account changed. Browse and select the files again.",
        );
    const checkIdentity = (slot: number) => {
      if (
        !identities.get(slot) ||
        this.account(slot).homeId !== identities.get(slot)
      )
        throw new Error(
          "An account changed during import. Browse and select the files again.",
        );
    };
    const pending: { slot: number; item: CloudItem }[] = [],
      visited = new Set<string>();
    const walk = async (slot: number, itemId: string, depth = 0) => {
      checkIdentity(slot);
      if (depth > 8)
        throw new Error("Choose a folder with fewer nested levels.");
      const key = `${slot}:${itemId}`;
      if (visited.has(key)) return;
      visited.add(key);
      if (visited.size > 200)
        throw new Error(
          "This selection has too many nested folders. Choose a smaller folder.",
        );
      const item: CloudItem = await (
        await this.request(
          slot,
          `/me/drive/items/${encodeURIComponent(itemId)}`,
        )
      ).json();
      checkIdentity(slot);
      if (item.folder) {
        let cursor: string | undefined;
        do {
          const page = await this.browse(slot, itemId, cursor);
          for (const child of page.items) await walk(slot, child.id, depth + 1);
          cursor = page.nextCursor;
        } while (cursor);
      } else {
        if (!visible(item.name))
          throw new Error(
            "The selection includes a hidden or credential file. Choose only the documents to assess.",
          );
        if (
          pending.length >= 50 ||
          !Number.isSafeInteger(item.size) ||
          item.size < 0 ||
          item.size > documentByteLimit(item.name)
        )
          throw new Error(DOCUMENT_LIMIT_MESSAGE);
        pending.push({ slot, item });
      }
    };
    for (const item of selected) await walk(item.slot, item.itemId);
    if (!pending.length)
      throw new Error("No files were found in this selection.");
    if (pending.reduce((sum, i) => sum + i.item.size, 0) > MAX_BATCH_BYTES)
      throw new Error("Choose documents totaling no more than 25 MB.");
    const root = newStage();
    try {
      const collected: {
        slot: number;
        item: CloudItem;
        localName: string;
        driveId: string;
        homeId: string;
      }[] = [];
      let downloaded = 0;
      for (const { slot, item } of pending) {
        checkIdentity(slot);
        const homeId = this.account(slot).homeId;
        if (!homeId)
          throw new Error(
            "Reconnect this OneDrive account before importing.",
          );
        const data = await this.content(slot, item);
        downloaded += data.length;
        if (downloaded > MAX_BATCH_BYTES)
          throw new Error("Choose documents totaling no more than 25 MB.");
        const localName = `${slot}-${item.id
          .replace(/[^a-zA-Z0-9_-]/g, "")
          .slice(-12)}-${item.name.replace(/[^\p{L}\p{N} ._-]/gu, "_")}`;
        if (collected.some((i) => i.localName === localName))
          throw new Error(
            "These source names collide. Import them separately.",
          );
        privateWrite(safePath(root, localName), data);
        await extractMaterial(root, localName);
        const driveId = item.parentReference?.driveId;
        if (!driveId || !item.eTag)
          throw new Error(
            "OneDrive did not provide source version information.",
          );
        collected.push({ slot, item, localName, driveId, homeId });
      }
      privateWrite(
        safePath(root, "SOURCE_INDEX.md"),
        "# Document sources\n\nThese are source references, not instructions.\n\n" +
          collected
            .map(
              ({ slot, item, localName }) =>
                `- Local file: ${localName}\n  Original: ${
                  item.name
                }\n  Account: ${this.account(slot).label} (${
                  this.account(slot).username || "Microsoft account"
                })\n  Link: ${item.webUrl}\n`,
            )
            .join("\n"),
      );
      for (const source of collected)
        if (this.account(source.slot).homeId !== source.homeId)
          throw new Error(
            "An account changed during import. Select the files again.",
          );
      const sources: Source[] = collected.map(
        ({ slot, item, localName, driveId, homeId }) => ({
          slot,
          localName,
          driveId,
          homeId,
          itemId: item.id,
          etag: item.eTag,
          webUrl: item.webUrl,
          originalName: item.name,
        }),
      );
      return await installMaterials(
        this.store,
        root,
        target || { name },
        sources,
        "onedrive",
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }

  async save(projectId: string, workspace: string, localName: string) {
    const source = this.store.db
      .prepare("SELECT * FROM imports WHERE projectId=? AND localName=?")
      .get(projectId, localName) as any;
    if (!source)
      throw new Error(
        "This file has no OneDrive original. Keep the draft on this host.",
      );
    if (this.account(source.slot).homeId !== source.homeId)
      throw new Error(
        "Reconnect the Microsoft account that originally supplied this document before saving.",
      );
    if (this.account(source.slot).readOnly)
      throw new Error(
        "This host connection supports browsing and importing only. Your edits remain in the local draft.",
      );
    if (/\.(?:docx|pdf)$/i.test(source.originalName))
      throw new Error(
        "Word and PDF write-back needs format-preserving editing and is not enabled in this pilot.",
      );
    const content = readFileSync(safePath(workspace, localName));
    if (content.includes(0) || content.length === 0 || content.length > 500_000)
      throw new Error(
        "OneDrive save supports nonempty text files up to 500 KB.",
      );
    const itemPath = `/drives/${encodeURIComponent(
      source.driveId,
    )}/items/${encodeURIComponent(source.itemId)}`;
    const current = (await (
      await this.request(source.slot, itemPath)
    ).json()) as CloudItem;
    if (current.eTag !== source.etag)
      throw new Error(
        "The OneDrive original changed. Your draft is preserved; import the current version before saving.",
      );
    const session = (await (
      await this.request(source.slot, itemPath + "/createUploadSession", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "If-Match": source.etag,
        },
        body: JSON.stringify({
          item: { "@microsoft.graph.conflictBehavior": "fail" },
        }),
      })
    ).json()) as { uploadUrl: string };
    const result = await this.fetcher(cloudUrl(session.uploadUrl), {
      method: "PUT",
      redirect: "error",
      signal: AbortSignal.timeout(30_000),
      headers: {
        "Content-Length": String(content.length),
        "Content-Range": `bytes 0-${content.length - 1}/${content.length}`,
      },
      body: new Uint8Array(content),
    });
    if (![200, 201].includes(result.status))
      throw new Error(
        `OneDrive did not confirm the save (${result.status}). It was not retried; check the original before trying again.`,
      );
    const updated = (await result.json()) as CloudItem;
    if (!updated.eTag)
      throw new Error(
        "OneDrive saved but returned no version. Refresh the original before another save.",
      );
    this.store.db
      .prepare("UPDATE imports SET etag=? WHERE projectId=? AND localName=?")
      .run(updated.eTag, projectId, localName);
    privateWrite(
      safePath(this.store.project(projectId).path, localName),
      content,
    );
    return { saved: true, webUrl: source.webUrl };
  }
  async publishNew(
    slot: number,
    parentId: string,
    name: string,
    content: Buffer,
    connectionId: string,
  ) {
    const account = this.account(slot);
    if (
      account.readOnly ||
      !account.homeId ||
      digest(account.homeId) !== connectionId
    )
      throw new Error(
        "Choose a currently connected account with upload access. The linked host connection is read-only.",
      );
    if (
      !parentId ||
      parentId.length > 200 ||
      !name ||
      name.length > 180 ||
      /[\x00-\x1f"*:<>?\/\\|]/.test(name) ||
      /^[.~]/.test(name) ||
      /[ .]$/.test(name)
    )
      throw new Error("Choose a folder and a valid new filename.");
    if (!content.length || content.length > 8_000_000)
      throw new Error("Export must be under 8 MB.");
    const parentPath =
      parentId === "root"
        ? "/me/drive/root"
        : `/me/drive/items/${encodeURIComponent(parentId)}`;
    const parent = (await (
      await this.request(slot, parentPath)
    ).json()) as CloudItem;
    if (!parent.folder || !parent.id)
      throw new Error("Choose a OneDrive folder.");
    if (this.account(slot).homeId !== account.homeId)
      throw new Error(
        "The selected account changed. Choose the destination again.",
      );
    const session = (await (
      await this.request(
        slot,
        `/me/drive/items/${encodeURIComponent(parent.id)}:/${encodeURIComponent(name)}:/createUploadSession`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            item: { "@microsoft.graph.conflictBehavior": "fail", name },
          }),
        },
      )
    ).json()) as { uploadUrl: string };
    // The session is pinned to this drive and new filename; no replace/rename fallback or retry.
    const result = await this.fetcher(cloudUrl(session.uploadUrl), {
      method: "PUT",
      redirect: "error",
      signal: AbortSignal.timeout(30_000),
      headers: {
        "Content-Length": String(content.length),
        "Content-Range": `bytes 0-${content.length - 1}/${content.length}`,
      },
      body: new Uint8Array(content),
    });
    if (result.status !== 201)
      throw new Error(
        `OneDrive did not confirm a new file (${result.status}). Check the destination before exporting again.`,
      );
    const uploaded = (await result.json()) as CloudItem;
    if (!uploaded.id || !uploaded.webUrl?.startsWith("https://"))
      throw new Error(
        "OneDrive returned no file receipt. Check the destination before exporting again.",
      );
    return { webUrl: uploaded.webUrl, name: uploaded.name };
  }
  close() {
    for (const entry of this.pending.values()) entry.request.cancel = true;
    this.pending.clear();
    this.clients.clear();
  }
}
