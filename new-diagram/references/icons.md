# Icons

Icons tell the reader *which technology* a node is: this box is Lambda, that cylinder is Postgres. They never replace the house style. A node with an icon is still a `svc`, `store`, `external`… box with an icon inside it.

Diagrams reference icons by **class name only**, never by URL or path. The catalog of available classes is `assets/icon-registry.tsv`. Nothing is downloaded up front: an icon is fetched the first time a diagram uses its class (see "How icons get onto disk").

```d2
...@_style   # house style classes (svc, store, external, critical, …)
...@_icons   # icon classes (aws-lambda, postgres, stripe, …)

parse: Parse statement { class: [svc; aws-lambda] }
ledger: Ledger { class: [store; postgres] }
stripe: Stripe { class: [external; stripe] }
```

Icon classes set only `icon`, so they stack with any style class. Put the style class first.

## Rules

1. **Evidence before icon.** Add an icon only when the code names the technology: an SDK import, a client constructor, an IaC resource, a connection string, a `docker-compose` image. See "Detecting the technology" below.
2. **Inferred nodes get no icon.** An icon claims certainty. A node marked `inferred` keeps the generic shape, even if you suspect the technology.
3. **Generic concepts get no icon.** "Worker", "Queue" or "Cache" with no named technology is a plain `svc` / `store` box.
4. **One icon per node.** Containers may carry an icon too, e.g. `class: [boundary; aws-vpc]` on a VPC. D2 puts a container's icon at its top-left.
5. **Never `shape: image`.** It drops the box, the border and the style. Always a style class plus an icon class.
6. **Never inline `icon:` in a diagram.** If a class is missing, add it to the registry (see "Adding an icon") and use the class.
7. **Don't move icons.** Leave placement to D2. Only intervene if the quality check shows a collision with the label.
8. **The label still names the thing.** `Ledger DB`, not an empty box with a Postgres logo. The icon adds to the label; it never stands in for it.
9. **Never edit a repo's `_icons.d2` by hand.** `scripts/icons.py` regenerates it from the files in `icons/`.

## Where icons come from

Look up a technology in this order and stop at the first hit:

| # | Source | Use it for | Browse | Path pattern | License |
|---|---|---|---|---|---|
| 1 | `icon-registry.tsv` | Anything already there | `grep -i 'name' assets/icon-registry.tsv` | — | — |
| 2 | **Terrastruct icons** | AWS, GCP, Azure services (official vendor icon sets) | https://icons.terrastruct.com | `https://icons.terrastruct.com/<provider>%2F<Category>%2F<Service>.svg` (URL-encoded `/` and spaces) | Each vendor's architecture-icon terms (allowed for architecture diagrams) |
| 3 | **Devicon** (pinned `v2.17.0`) | Languages, frameworks, databases, brokers, infra tools, many SaaS | https://devicon.dev | `https://cdn.jsdelivr.net/gh/devicons/devicon@v2.17.0/icons/<name>/<name>-original.svg` | MIT; logos are their owners' trademarks |
| 4 | **Simple Icons** (pinned `16.35.0`) | Brands missing from Devicon (Stripe, Auth0, Clerk…) | https://simpleicons.org | `https://cdn.jsdelivr.net/npm/simple-icons@16.35.0/icons/<slug>.svg` | CC0; logos are their owners' trademarks |
| 5 | **No icon** | Anything not found above | — | — | — |

Notes per source:

- **Terrastruct:** use the base service icon (`AWS-Lambda.svg`). The `_light-bg` and `_<Resource>` variants (e.g. `…SQS_Queue_light-bg.svg`) are resource-level glyphs. Use them only when the diagram is about that specific resource.
- **Devicon:** prefer `-original` (colored) over `-plain`. Avoid `-wordmark` variants, because the logo text duplicates the label. A few icons only exist as `-plain` (`django`, `rails`, `graphql`). `grpc` uses `-plain` because its `-original` file loses its shapes when cleaned.
- **Simple Icons:** brands do get removed from this set over time (OpenAI, Slack, Twilio and SendGrid are gone in v16). Always probe a slug before adding it. The glyphs ship black; the registry's `color` column (the brand hex from the package's `data/simple-icons.json`) is applied as their fill.

## How icons get onto disk

`scripts/render-fit.sh` runs `scripts/icons.py ensure <diagram.d2>` before every render. For each class the diagram uses that is in the registry, it checks, in order:

1. **`<diagram dir>/icons/<class>.svg|png`:** already in this repo, so reuse it.
2. **`<skill>/assets/icons/<class>.svg|png`:** cleaned earlier for another repo, so copy it.
3. **Otherwise:** download the pinned URL, clean it, validate it with a real `d2` PNG render, save it in the skill cache, and copy it into the repo.

It then regenerates `<diagram dir>/_icons.d2` from whatever is in `icons/`. The repo keeps its icons (commit `docs/diagrams/icons/`), so renders work offline and never change when an upstream file changes. The skill cache only ever holds icons some diagram actually used.

**What "clean" means:** D2's SVG importer (0.9.0) is stricter than browsers, so the cleaner:
- removes `<desc>`, `<title>`, `<metadata>`, `<mask>`, `<filter>`, editor namespaces, and unsupported style properties
- turns radial gradients into linear ones
- moves every gradient into `<defs>`
- adds missing stop offsets and coordinates, and inherits stops through `href`
- replaces gradients D2 can't render (`objectBoundingBox`) with their first color
- separates transform functions
- removes duplicate and unused IDs
- applies the brand color to Simple Icons

Anything that still fails validation is rasterized to a 256px PNG.

**Tested on the whole registry:** all 133 icons pass. 131 stay SVG; `linux` and `azure-redis` become PNG because they exceed D2's 64KB icon limit. They were checked by eye on a contact sheet as well.

To test icons without touching the skill cache:
```bash
NEW_DIAGRAM_ICON_CACHE=/tmp/icon-test python3 scripts/icons.py check aws-lambda postgres stripe
```

## Adding an icon

1. Find it through the lookup order above.
2. Add one tab-separated row to `assets/icon-registry.tsv`: class, group, source, pinned URL, and the brand color (Simple Icons only). Naming:
   - cloud services: `<provider>-<service>`, e.g. `aws-sqs`, `gcp-pubsub`, `azure-service-bus`
   - everything else: the plain product name, e.g. `postgres`, `kafka`, `nextjs`, `stripe`
   - kebab-case, no version numbers, no vendor prefix for non-cloud tech
3. Never use an unpinned version (`@latest`, a bare `simple-icons`, `cdn.simpleicons.org`).
4. Run `python3 scripts/icons.py check <class>`. It must print `downloaded`, not `FAILED`.
5. Add the class name to the catalog below.

## Detecting the technology

These are typical code signals and the class each one maps to. Treat them as examples of what counts as evidence, not a complete list.

| Signal in the repo | Class |
|---|---|
| `@aws-sdk/client-s3`, `boto3.client("s3")`, Terraform `aws_s3_bucket`, CDK `s3.Bucket` | `aws-s3` |
| `serverless.yml` `functions:`, SAM `AWS::Serverless::Function`, `aws_lambda_function` | `aws-lambda` |
| `@aws-sdk/client-sqs`, `aws_sqs_queue` | `aws-sqs` |
| `@aws-sdk/client-dynamodb`, `aws_dynamodb_table` | `aws-dynamodb` |
| `@google-cloud/pubsub`, `google_pubsub_topic` | `gcp-pubsub` |
| `@azure/service-bus`, `azurerm_servicebus_namespace` | `azure-service-bus` |
| `pg`, `psycopg`, `asyncpg`, `DATABASE_URL=postgres://`, compose `image: postgres` | `postgres` |
| `ioredis`, `redis-py`, `REDIS_URL`, compose `image: redis` | `redis` |
| `kafkajs`, `confluent_kafka`, `spring-kafka` | `kafka` |
| `amqplib`, `pika`, compose `image: rabbitmq` | `rabbitmq` |
| `stripe` SDK import, `STRIPE_SECRET_KEY` | `stripe` |
| `@anthropic-ai/sdk`, `anthropic` Python package | `anthropic` |
| `Dockerfile`, compose services | `docker` (on the container, not every node) |
| Helm `Chart.yaml`, k8s manifests | `kubernetes` / `helm` |

A runtime or framework icon (`nodejs`, `django`, `nextjs`) goes on a service only when the diagram's audience cares about the stack, e.g. in a containers diagram. In a data-flow or sequence diagram it's noise; leave it off.

## Catalog (classes in `icon-registry.tsv`)

**AWS:** `aws-lambda` `aws-ec2` `aws-ecs` `aws-eks` `aws-fargate` `aws-ecr` `aws-s3` `aws-dynamodb` `aws-rds` `aws-aurora` `aws-elasticache` `aws-sqs` `aws-sns` `aws-eventbridge` `aws-step-functions` `aws-kinesis` `aws-api-gateway` `aws-cloudfront` `aws-route53` `aws-elb` `aws-vpc` `aws-cognito` `aws-secrets-manager` `aws-cloudwatch` `aws-ses` `aws-sagemaker`

**GCP:** `gcp-cloud-run` `gcp-cloud-functions` `gcp-cloud-storage` `gcp-pubsub` `gcp-bigquery` `gcp-cloud-sql` `gcp-firestore` `gcp-spanner` `gcp-memorystore` `gcp-cloud-tasks` `gcp-cloud-scheduler` `gcp-load-balancing` `gcp-cloud-cdn`

**Azure:** `azure-functions` `azure-aks` `azure-container-instances` `azure-blob-storage` `azure-cosmos-db` `azure-sql` `azure-redis` `azure-service-bus` `azure-event-hubs` `azure-api-management` `azure-front-door`

**Datastores & messaging:** `postgres` `mysql` `mariadb` `sqlite` `mongodb` `redis` `memcached` `cassandra` `elasticsearch` `neo4j` `influxdb` `kafka` `rabbitmq` `nats` `airflow` `spark`

**Platform & delivery:** `docker` `kubernetes` `helm` `terraform` `pulumi` `ansible` `nginx` `linux` `cloudflare` `vercel` `firebase` `supabase` `github` `github-actions` `gitlab` `jenkins` `argocd`

**Observability:** `prometheus` `grafana` `opentelemetry` `kibana` `sentry` `datadog`

**Runtimes & languages:** `nodejs` `bun` `typescript` `python` `go` `java` `kotlin` `rust` `ruby` `php` `elixir` `dotnet`

**Frameworks & protocols:** `react` `nextjs` `vue` `angular` `svelte` `express` `nestjs` `django` `flask` `fastapi` `rails` `laravel` `spring` `prisma` `sqlalchemy` `graphql` `grpc` `trpc` `socketio`

**SaaS & third parties:** `slack` `twilio` `okta` `stripe`* `anthropic`* `auth0`* `clerk`* `resend`* `posthog`* `temporal`* `snowflake`* `clickhouse`* `shopify`*

\* Simple Icons, recolored to the brand color.

**Known gaps (no pinned source found, so no icon):** OpenAI, SendGrid, Plaid, Segment, GKE (use `kubernetes`), MinIO, Celery, Deno.

## Rendering

- Icons are local files, embedded into the SVG at render time. Only the first use of an icon needs network access.
- Icons do **not** change with the light/dark theme.

### Dark mode

- Terrastruct and Devicon icons are colored and read fine on both the light (`#FFFFFF`) and dark (`#161B22`) node fills, and so do Simple Icons with a colored brand (Stripe, Auth0, Clerk, Snowflake, Shopify, ClickHouse).
- **Near-black brands** (`anthropic`, `posthog`, `resend`, `temporal`) nearly disappear on the dark fill. When the dark render is built, these need a light variant (`<class>.dark.svg`, recolored to `#E6EDF3`), picked by the dark palette. Not built yet.
