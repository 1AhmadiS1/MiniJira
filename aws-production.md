# MiniJira AWS Production Plan

This document records the AWS and Docker production discussion. It is a plan,
not a record of resources already deployed. No EC2, ECR, RDS, ElastiCache, S3,
DNS, or TLS resource has been created by the repository changes.

## Live deployment checkpoint - 2026-07-14

### Where we are

```text
Phase 1 - Secure/configure AWS account:  COMPLETE
Phase 2 - Repository preparation:        COMPLETE
Phase 3 - Create security groups:        AWAITING USER APPROVAL
Phase 4 onward - AWS resources/deploy:   NOT STARTED
```

No MiniJira infrastructure has been created and no deployment resource is
currently consuming promotional credits.

### What we did - account and access

- Selected **Europe (Frankfurt), `eu-central-1`** and will keep MiniJira
  resources there unless Console eligibility requires a change.
- Root MFA is enabled, root has no access keys, and root is reserved for
  account-only operations.
- Created the MFA-protected `minijira-admin` IAM user for daily work.
- Configured `aws login --profile minijira-admin`, providing a temporary
  browser-authenticated CLI session without permanent access keys.
- Confirmed Free Tier notifications are enabled; budget creation was deferred.
- Kept the account on its promotional-credit Free Plan. IAM Identity Center
  with AWS Organizations was not enabled because joining an organization would
  upgrade this Free Plan and expire its remaining credits.

### What we did - production preparation

- Production Compose pulls `${ECR_IMAGE}` and excludes Docker PostgreSQL.
  Development still builds locally with Docker PostgreSQL and Redis.
- Production can use ElastiCache through `REDIS_URL` or the memory-limited
  `local-redis` profile.
- Gunicorn workers/timeouts are configurable, starting at two workers for a
  small EC2 instance.
- Migrations and static collection are explicit one-off deployment commands.
- Added `GET /health/` for database/cache checks and container health ordering.
- HTTPS-only Django settings remain off until Nginx TLS is verified.
- Real environment files and AWS credentials remain outside Git; tracked
  environment templates contain placeholders only.

### Verification completed

- Full suite: **128 tests passed**.
- Django checks and development/production Compose validation passed.
- The image builds successfully, is approximately 90 MB, runs as non-root
  `django`, and passes Django's system check inside the container.

### Phase 3 inspection and next action

A read-only inspection found one default VPC, three default public subnets, and
only the default security group in Frankfurt. No AWS changes were made.

Pending explicit approval, create:

1. `minijira-ec2-sg`: public inbound 80/443 only; prefer AWS Systems Manager
   Session Manager over opening SSH 22.
2. `minijira-rds-sg`: inbound 5432 only from `minijira-ec2-sg`.
3. `minijira-cache-sg`: inbound 6379 only from `minijira-ec2-sg` if managed
   ElastiCache is used.

Security groups do not consume promotional credits, but creating them changes
shared AWS infrastructure and therefore requires explicit approval.

## Goal

Deploy MiniJira using services that the AWS Console explicitly shows as
eligible for this account's Free Plan / Free Tier or that can stay within its
promotional credits.

AWS changed its Free Tier model for accounts created after July 15, 2025. New
accounts receive credits and the Free Plan lasts up to six months or until its
credits are exhausted. Eligibility and estimated cost must therefore be checked
in the account's AWS Console before each resource is created.

Official references:

- AWS Free Tier: https://aws.amazon.com/free/
- Free Tier documentation:
  https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html
- ECR pricing: https://aws.amazon.com/ecr/pricing/

## Selected production-style architecture

```text
Local computer / GitHub Actions
        |
        | docker push
        v
Private Amazon ECR
        |
        | authenticated image pull
        v
EC2: Nginx + Django/Gunicorn
        |                    |
        |                    +----------> Private S3 attachments
        |
        +----------> RDS PostgreSQL
        |
        +----------> ElastiCache Redis/Valkey (if eligible)
                      OR Redis container on EC2 (fallback)
```

Use the same AWS region for ECR, EC2, RDS, ElastiCache, and S3. This avoids
cross-region complexity and charges.

## What each AWS service does

### Private Amazon ECR

ECR stores Docker images; it does not run containers. A private repository is
accessible only to authenticated IAM principals and AWS services.

- Planned repository name: `minijira`.
- AWS provides a URI like:
  `123456789012.dkr.ecr.eu-west-1.amazonaws.com/minijira`.
- New ECR customers currently receive 500 MB/month of private repository
  storage for one year under the documented offer.
- ECR-to-EC2 transfer in the same region is free according to ECR pricing.
- The current local image was shown by Docker as approximately 389 MB, while
  ECR's billed compressed-layer size may differ.
- Add a lifecycle policy that retains only the latest 2-3 images.
- A public ECR repository has a larger free allowance, but it would make the
  application image publicly downloadable; private ECR is preferred.

### Amazon EC2

EC2 is the Linux server that runs the application containers:

- Nginx
- Django/Gunicorn
- Redis only if ElastiCache is not eligible

Select an instance type explicitly marked eligible in this account's Console.
For a small-memory instance, use one or two Gunicorn workers and limit Redis
memory. Add swap if necessary.

EC2 security-group ingress:

| Port | Source | Purpose |
|---|---|---|
| 22 | Administrator's IP only | SSH |
| 80 | Public | HTTP / certificate setup |
| 443 | Public | HTTPS |

Do not publicly expose PostgreSQL 5432, Redis 6379, or Gunicorn 8000.

### Amazon RDS for PostgreSQL

The AWS Console shows that this account can create a Free Tier-eligible RDS
database, so managed RDS is preferred over production PostgreSQL in Docker.

Choose only options shown as eligible and review the estimate before creation:

- PostgreSQL, current supported version
- Single-AZ
- Eligible micro instance class
- Eligible general-purpose storage amount
- No Multi-AZ standby
- No read replica
- No provisioned IOPS
- No paid monitoring/retention add-ons
- Not publicly accessible

Place RDS in the same VPC as EC2. Its security group should allow port 5432
only from the EC2 security group, never from `0.0.0.0/0`.

Production environment values will resemble:

```env
DB_NAME=minijira
DB_USER=minijira_admin
DB_PASSWORD=generated-rds-password
DB_HOST=minijira.xxxxxx.eu-west-1.rds.amazonaws.com
DB_PORT=5432
DB_CONN_MAX_AGE=60
DB_SSLMODE=require
```

The real endpoint is shown on the RDS `Connectivity & security` page.

### Redis on AWS

AWS provides two relevant managed services:

- **Amazon ElastiCache for Redis/Valkey**: appropriate for MiniJira's cache.
- **Amazon MemoryDB**: durable Redis-compatible database; unnecessary because
  PostgreSQL is MiniJira's system of record.

If the Console explicitly offers an eligible ElastiCache/Valkey option and its
estimate fits the Free Plan/credits, use it. Django then connects to its private
endpoint:

```env
REDIS_URL=redis://minijira-cache.xxxxxx.cache.amazonaws.com:6379/1
```

ElastiCache must be in the same VPC and should accept port 6379 only from the
EC2 security group. It must not be public.

If ElastiCache is not eligible, use the existing `redis:7-alpine` container on
EC2:

```env
REDIS_URL=redis://redis:6379/1
```

Redis currently supplies Django's cache backend only. API responses are not
automatically cached, and losing cache data does not lose primary MiniJira data.
The EC2 fallback should use a 64-128 MB limit and an eviction policy rather than
consume all instance memory.

### Private Amazon S3

S3 stores issue attachments so files survive application replacement and do
not depend on EC2 disk.

- Keep Block Public Access enabled.
- Use default encryption.
- Keep `AWS_QUERYSTRING_AUTH=True` for signed private URLs.
- Give EC2 an IAM role scoped only to the MiniJira bucket.
- Prefer an IAM role over access keys in `.env.production`.

Example:

```env
USE_S3=True
AWS_STORAGE_BUCKET_NAME=minijira-production-attachments-unique-name
AWS_S3_REGION_NAME=eu-west-1
AWS_S3_CUSTOM_DOMAIN=
AWS_QUERYSTRING_AUTH=True
```

## Image build and deployment flow

Do not build the production image on a very small EC2 instance. Build on the
development computer or later in GitHub Actions, push to private ECR, and let
EC2 pull it.

The image architecture must match EC2:

```powershell
# x86 EC2
docker buildx build --platform linux/amd64 -t minijira:latest --load .

# ARM EC2
docker buildx build --platform linux/arm64 -t minijira:latest --load .
```

Typical ECR flow (replace account ID and region):

```powershell
aws ecr get-login-password --region eu-west-1 |
docker login --username AWS --password-stdin `
  123456789012.dkr.ecr.eu-west-1.amazonaws.com

docker tag minijira:latest `
  123456789012.dkr.ecr.eu-west-1.amazonaws.com/minijira:latest

docker push `
  123456789012.dkr.ecr.eu-west-1.amazonaws.com/minijira:latest
```

ECR reduces build-cache and intermediate-layer use on EC2, but EC2 still needs
local disk for the pulled image and running container. Remove unused images
with `docker image prune -f`; never casually prune database volumes.

## Production environment

Create the ignored production file from the tracked template:

```bash
cp .env.production.example .env.production
```

Required sources for values:

| Variable | Source |
|---|---|
| `SECRET_KEY` | Generate with Django's `get_random_secret_key()` |
| `ALLOWED_HOSTS` | Production API domain |
| `CSRF_TRUSTED_ORIGINS` | Production HTTPS origin |
| `DB_*` | RDS creation values and endpoint |
| `REDIS_URL` | ElastiCache endpoint or Docker Redis service name |
| `AWS_STORAGE_BUCKET_NAME` | Created private S3 bucket |
| `AWS_S3_REGION_NAME` | Region containing the bucket |
| `ECR_IMAGE` | Private ECR repository URI plus image tag |

Never commit `.env.production` or AWS credentials.

## DNS and HTTPS

Nginx currently listens on port 80 only. Before real deployment:

1. Point the API domain to EC2.
2. Issue a free Let's Encrypt certificate or use another TLS terminator.
3. Add the real domain and certificate paths to Nginx.
4. Open port 443.
5. Enable Django's HTTPS-only settings only after TLS works.

Enabling `SECURE_SSL_REDIRECT=True` before HTTPS works causes redirects to an
unavailable endpoint.

## Cost and security controls

Before creating resources:

1. Enable root-account MFA.
2. Create AWS Budget alerts at small thresholds such as $1, $5, and $10.
3. Check the Console's eligibility label and monthly estimate for every option.
4. Avoid Multi-AZ, NAT Gateway, load balancers, extra storage, cross-region
   traffic, and paid monitoring unless deliberately budgeted.
5. Keep EC2, RDS, ElastiCache, ECR, and S3 in one region.
6. Do not process real sensitive user data on an evaluation Free Plan.

## Repository status and remaining code work

Already implemented:

- Dockerfile and non-root image
- Shared/development/production Compose split
- Gunicorn and Nginx
- Redis-capable Django cache configuration
- Environment-driven database, JWT, S3, and HTTPS/security settings
- Development and production environment templates
- Successful Docker build and Compose validation
- 127 passing tests at the time Docker support was added

Still required after final AWS choices are confirmed:

1. Keep Docker PostgreSQL in development, but exclude it from the RDS-backed
   production stack.
2. Remove production Django's dependency on the Compose `db` service.
3. Make production use `ECR_IMAGE` while development continues to `build: .`.
4. Support either an ElastiCache endpoint or the Redis container based on the
   final eligibility decision.
5. Lower/configure Gunicorn workers for the selected EC2 memory size.
6. Add the real TLS Nginx configuration after the domain is known.
7. Run migrations as one deployment task rather than from every future web
   replica.
8. Add application/container health checks and complete a production smoke test.

## Current unresolved decision

Check the ElastiCache creation page in this AWS account. If it explicitly shows
an eligible Redis/Valkey option with an acceptable estimate, use managed
ElastiCache. Otherwise, use the existing Redis Docker container on EC2. Do not
use MemoryDB for this project.


---

## Detailed execution runbook

Follow these phases in order and verify each phase before continuing. Do not
create every AWS resource at once. Use the same AWS region for all resources.

### Phase 1 - Secure and configure the AWS account

1. Choose one nearby region that shows the required eligible resources.
2. Enable MFA for the AWS root account.
3. Do not use the root account for normal work.
4. Create AWS Budget alerts at $1, $5, and $10.
5. Enable Free Tier usage notifications.
6. Install AWS CLI locally and configure an authorized non-root identity.
7. Verify it:

```powershell
aws --version
aws sts get-caller-identity
```

Never commit AWS CLI credentials or copy them into project `.env` files.

### Phase 2 - Finish repository preparation

Before AWS deployment, update the repository so:

1. Development keeps Docker PostgreSQL, Docker Redis, and `build: .`.
2. Production does not start Docker PostgreSQL when using RDS.
3. Production pulls `${ECR_IMAGE}` instead of building on EC2.
4. Production can use an ElastiCache endpoint or optional Docker Redis.
5. Gunicorn workers/timeouts are configurable for small EC2 memory.
6. Migrations run once as a deployment command, not on every web restart.
7. Django has an application/database/cache health endpoint.

### Phase 3 - Create security groups

Create `minijira-ec2-sg`:

| Port | Source | Purpose |
|---|---|---|
| 22 | Administrator's IP only | SSH |
| 80 | `0.0.0.0/0` | HTTP and certificate setup |
| 443 | `0.0.0.0/0` | HTTPS |

Create `minijira-rds-sg` with PostgreSQL port 5432 allowed only from
`minijira-ec2-sg`.

If using ElastiCache, create `minijira-cache-sg` with TCP port 6379 allowed only
from `minijira-ec2-sg`.

Never expose ports 5432, 6379, or 8000 publicly.

### Phase 4 - Create RDS PostgreSQL

In `RDS -> Databases -> Create database`, choose only options shown as eligible:

- PostgreSQL, current supported version
- Single-AZ
- Eligible micro instance class
- Eligible general-purpose storage amount
- Database identifier `minijira-db`
- Master user such as `minijira_admin`
- Initial database `minijira`
- Same VPC as EC2
- `minijira-rds-sg`
- Public access disabled
- No read replica, Multi-AZ, provisioned IOPS, or paid monitoring add-ons

Review the displayed cost estimate before creation. After RDS is available,
copy its endpoint from `Connectivity & security` and save these values for the
production environment:

```env
DB_NAME=minijira
DB_USER=minijira_admin
DB_PASSWORD=generated-rds-password
DB_HOST=minijira-db.xxxxxx.region.rds.amazonaws.com
DB_PORT=5432
DB_CONN_MAX_AGE=60
DB_SSLMODE=require
```

### Phase 5 - Check ElastiCache eligibility

In the ElastiCache creation page, check the account-specific eligibility and
estimate. If eligible, use a single small Redis/Valkey-compatible cache in the
same VPC with `minijira-cache-sg`, no public access, replicas, or Multi-AZ.

```env
REDIS_URL=redis://minijira-cache.xxxxxx.cache.amazonaws.com:6379/1
```

If it is not eligible, keep Redis in Docker on EC2:

```env
REDIS_URL=redis://redis:6379/1
```

Limit Docker Redis to roughly 64-128 MB with an eviction policy. Do not use
MemoryDB; MiniJira stores durable data in PostgreSQL.

### Phase 6 - Create the private S3 bucket

Create a globally unique bucket in the selected region. Keep Block Public
Access enabled and default encryption on. Do not add a public bucket policy.

```env
USE_S3=True
AWS_STORAGE_BUCKET_NAME=minijira-production-attachments-unique-name
AWS_S3_REGION_NAME=chosen-region
AWS_S3_CUSTOM_DOMAIN=
AWS_QUERYSTRING_AUTH=True
```

### Phase 7 - Create the EC2 IAM role

Create `minijira-ec2-role` trusted by EC2. Attach
`AmazonEC2ContainerRegistryReadOnly` for private ECR pulls.

Add a custom S3 policy restricted to the MiniJira bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::BUCKET_NAME"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::BUCKET_NAME/*"]
    }
  ]
}
```

This allows Django to use S3 without static AWS keys in `.env.production`.

### Phase 8 - Create private ECR

In `ECR -> Private registry -> Repositories`, create `minijira` with private
visibility and default AES-256 encryption. Record the repository URI:

```text
123456789012.dkr.ecr.region.amazonaws.com/minijira
```

Add a lifecycle policy that retains only the newest 2-3 images. Prefer
versioned tags (`v1`, `v2`, or a Git commit SHA) over relying only on `latest`.

### Phase 9 - Build and push the image

Build for the EC2 architecture:

```powershell
# x86 EC2
docker buildx build --platform linux/amd64 -t minijira:latest --load .

# ARM EC2
docker buildx build --platform linux/arm64 -t minijira:latest --load .
```

Authenticate, tag, and push (replace placeholders):

```powershell
aws ecr get-login-password --region REGION |
docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.REGION.amazonaws.com

docker tag minijira:latest ACCOUNT.dkr.ecr.REGION.amazonaws.com/minijira:v1
docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/minijira:v1
```

Verify the image appears in ECR.

### Phase 10 - Create EC2

Launch an eligible Ubuntu instance in the same VPC. Attach:

- `minijira-ec2-sg`
- `minijira-ec2-role`
- An SSH key pair
- Only eligible EBS storage

Install Docker Engine, the Docker Compose plugin, Git, and AWS CLI. Verify:

```bash
docker --version
docker compose version
aws --version
```

Add the Ubuntu user to the Docker group, then reconnect:

```bash
sudo usermod -aG docker ubuntu
```

### Phase 11 - Configure production on EC2

Clone the repository so EC2 has Compose and Nginx files:

```bash
git clone https://github.com/1AhmadiS1/MiniJira.git
cd MiniJira
cp .env.production.example .env.production
chmod 600 .env.production
```

Fill `.env.production` with the generated secret, domain, RDS endpoint and
credentials, Redis endpoint, S3 bucket/region, and versioned ECR URI.

Before HTTPS works, temporarily keep:

```env
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=0
TRUST_PROXY_HEADERS=False
```

### Phase 12 - Pull and launch the application

Authenticate EC2 to ECR using its IAM role:

```bash
aws ecr get-login-password --region REGION | docker login \
  --username AWS --password-stdin ACCOUNT.dkr.ecr.REGION.amazonaws.com
```

Pull the image:

```bash
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml pull
```

Run migrations once:

```bash
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm web python manage.py migrate --noinput
```

Collect static files:

```bash
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm web python manage.py collectstatic --noinput
```

Start and inspect:

```bash
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml up -d

docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
```

### Phase 13 - Configure DNS and HTTPS

1. Point an API-domain A record to the EC2 public address.
2. Verify HTTP and DNS before forcing HTTPS.
3. Issue a free Let's Encrypt certificate.
4. Mount the certificate into Nginx and add an HTTPS server on port 443.
5. Keep port 80 only for redirect/certificate renewal.

After HTTPS works, enable:

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=False
TRUST_PROXY_HEADERS=True
```

Then restart the stack.

### Phase 14 - Production verification

Verify all of these:

1. Swagger/API schema loads.
2. Registration, login, JWT refresh, and current-user endpoints work.
3. Workspace/member permissions still return expected 403/404 responses.
4. Projects, issues, comments, search, filters, and pagination work.
5. Attachments upload to S3 and use signed private URLs.
6. RDS and Redis/ElastiCache are not publicly accessible.
7. HTTP redirects to HTTPS after TLS is enabled.
8. Django's deployment check is reviewed:

```bash
docker compose exec web python manage.py check --deploy
```

### Phase 15 - Repeatable releases and rollback

For each release:

1. Run tests locally.
2. Build a new versioned image.
3. Push it to ECR.
4. Change `ECR_IMAGE` on EC2 to the new tag.
5. Pull the image.
6. Run migrations once.
7. Restart the stack and smoke-test it.

If it fails, restore the previous ECR tag and restart. Periodically run
`docker image prune -f` on EC2, but never casually prune Docker volumes.

### Exact recommended next order

1. Complete the remaining AWS-oriented repository changes.
2. Secure the AWS account and create budgets.
3. Pick one region.
4. Create security groups.
5. Create RDS.
6. Check ElastiCache eligibility and make the final Redis decision.
7. Create S3.
8. Create the EC2 IAM role.
9. Create private ECR.
10. Build and push the image.
11. Create EC2.
12. Configure `.env.production`.
13. Pull, migrate, collect static files, and launch.
14. Configure domain and HTTPS.
15. Run the full production smoke test.
