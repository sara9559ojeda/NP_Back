import * as fs from 'node:fs';
import * as path from 'node:path';

/** Where the backend reads its PostgreSQL database from. */
export type DatabaseMode = 'rds' | 'external';
export type CpuArchitectureName = 'X86_64' | 'ARM64';

export interface DatabaseParameters {
  /** `rds` creates Amazon RDS for PostgreSQL; `external` reuses a database such as Supabase. */
  readonly mode: DatabaseMode;
  /** Secrets Manager secret (name) that holds the full NP_DATABASE_URL when mode is `external`. */
  readonly externalSecretName: string;
  readonly instanceClass: string;
  readonly allocatedStorageGiB: number;
  readonly maxAllocatedStorageGiB: number;
  readonly backupRetentionDays: number;
  readonly multiAz: boolean;
  readonly deletionProtection: boolean;
}

export interface BackendParameters {
  /** Fargate CPU units (256 = 0.25 vCPU). */
  readonly cpu: number;
  readonly memoryMiB: number;
  readonly desiredCount: number;
  readonly cpuArchitecture: CpuArchitectureName;
  /** Run tasks on Fargate Spot (cheaper, can be interrupted). */
  readonly useSpot: boolean;
  readonly logRetentionDays: number;
}

export interface FrontendParameters {
  /** NP_Front checkout, relative to the NP_Back repository root. */
  readonly sourceDir: string;
}

export interface DeploymentParameters {
  /** Lowercase prefix for stack and resource names. */
  readonly projectName: string;
  /** Target account; empty uses the account of the current AWS credentials. */
  readonly account: string;
  readonly region: string;
  /** Optional e-mail for alarms and the monthly budget; empty disables both. */
  readonly alarmEmail: string;
  readonly monthlyBudgetUsd: number;
  readonly database: DatabaseParameters;
  readonly backend: BackendParameters;
  readonly frontend: FrontendParameters;
}

/** Root of the NP_Back repository (the Docker build context). */
export const BACKEND_ROOT = path.resolve(__dirname, '..', '..', '..');

const FARGATE_MEMORY_BY_CPU: Readonly<Record<number, readonly [number, number]>> = {
  256: [512, 2048],
  512: [1024, 4096],
  1024: [2048, 8192],
  2048: [4096, 16384],
};

type Json = Record<string, unknown>;

function section(source: Json, key: string): Json {
  const value = source[key];
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`parameters: "${key}" must be an object`);
  }
  return value as Json;
}

function text(source: Json, key: string, fallback?: string): string {
  const value = source[key] ?? fallback;
  if (typeof value !== 'string') throw new Error(`parameters: "${key}" must be a string`);
  return value.trim();
}

function integer(source: Json, key: string, min: number, max: number): number {
  const value = source[key];
  if (typeof value !== 'number' || !Number.isInteger(value) || value < min || value > max) {
    throw new Error(`parameters: "${key}" must be an integer between ${min} and ${max}`);
  }
  return value;
}

function flag(source: Json, key: string): boolean {
  const value = source[key];
  if (typeof value !== 'boolean') throw new Error(`parameters: "${key}" must be true or false`);
  return value;
}

function oneOf<T extends string>(source: Json, key: string, allowed: readonly T[]): T {
  const value = text(source, key);
  if (!(allowed as readonly string[]).includes(value)) {
    throw new Error(`parameters: "${key}" must be one of ${allowed.join(', ')}`);
  }
  return value as T;
}

function parseDatabase(source: Json): DatabaseParameters {
  const database: DatabaseParameters = {
    mode: oneOf(source, 'mode', ['rds', 'external'] as const),
    externalSecretName: text(source, 'externalSecretName', ''),
    instanceClass: text(source, 'instanceClass'),
    allocatedStorageGiB: integer(source, 'allocatedStorageGiB', 20, 1000),
    maxAllocatedStorageGiB: integer(source, 'maxAllocatedStorageGiB', 20, 1000),
    backupRetentionDays: integer(source, 'backupRetentionDays', 1, 35),
    multiAz: flag(source, 'multiAz'),
    deletionProtection: flag(source, 'deletionProtection'),
  };
  if (database.mode === 'external' && !database.externalSecretName) {
    throw new Error('parameters: database.externalSecretName is required when database.mode is "external"');
  }
  if (database.maxAllocatedStorageGiB < database.allocatedStorageGiB) {
    throw new Error('parameters: database.maxAllocatedStorageGiB must be >= allocatedStorageGiB');
  }
  return database;
}

function parseBackend(source: Json): BackendParameters {
  const cpu = integer(source, 'cpu', 256, 2048);
  const limits = FARGATE_MEMORY_BY_CPU[cpu];
  if (!limits) throw new Error('parameters: backend.cpu must be 256, 512, 1024 or 2048');
  return {
    cpu,
    memoryMiB: integer(source, 'memoryMiB', limits[0], limits[1]),
    desiredCount: integer(source, 'desiredCount', 1, 10),
    cpuArchitecture: oneOf(source, 'cpuArchitecture', ['X86_64', 'ARM64'] as const),
    useSpot: flag(source, 'useSpot'),
    logRetentionDays: integer(source, 'logRetentionDays', 1, 3653),
  };
}

/** Validate a parsed parameters document. Throws with a readable message on the first problem. */
export function parseParameters(source: Json): DeploymentParameters {
  const projectName = text(source, 'projectName');
  if (!/^[a-z][a-z0-9-]{1,20}$/.test(projectName)) {
    throw new Error('parameters: projectName must be 2-21 lowercase letters, digits or hyphens');
  }
  const account = text(source, 'account', '');
  if (account && !/^\d{12}$/.test(account)) throw new Error('parameters: account must be 12 digits or empty');
  const alarmEmail = text(source, 'alarmEmail', '');
  if (alarmEmail && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(alarmEmail)) {
    throw new Error('parameters: alarmEmail is not a valid e-mail address');
  }
  return {
    projectName,
    account,
    region: text(source, 'region'),
    alarmEmail,
    monthlyBudgetUsd: integer(source, 'monthlyBudgetUsd', 1, 10000),
    database: parseDatabase(section(source, 'database')),
    backend: parseBackend(section(source, 'backend')),
    frontend: { sourceDir: text(section(source, 'frontend'), 'sourceDir') },
  };
}

/** Read and validate the parameters file at `file` (relative paths resolve from infra/aws). */
export function loadParameters(file: string): DeploymentParameters {
  const absolute = path.resolve(__dirname, '..', file);
  if (!fs.existsSync(absolute)) {
    throw new Error(`Parameters file not found: ${absolute}. Copy parameters.example.json to parameters.json.`);
  }
  return parseParameters(JSON.parse(fs.readFileSync(absolute, 'utf8')) as Json);
}
