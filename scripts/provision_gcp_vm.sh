#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
: "${GCP_BILLING_ACCOUNT_ID:?Set GCP_BILLING_ACCOUNT_ID}"

case "${PROVISION_MODE:-verify}" in
  verify|create) ;;
  *) echo "Unsupported provision mode." >&2; exit 1 ;;
esac

name=vpnlens-demo
zone=us-central1-a
region=us-central1
subnet=vpnlens-us-central1
project=(--project="$GCP_PROJECT_ID" --quiet)

billing=$(gcloud billing projects describe "$GCP_PROJECT_ID" --quiet --format=json)
if ! jq -e --arg account "billingAccounts/$GCP_BILLING_ACCOUNT_ID" \
    '.billingEnabled == true and .billingAccountName == $account' <<< "$billing" >/dev/null; then
  echo "Billing is disabled or the project is linked to a different billing account." >&2
  exit 1
fi
echo "Verified active billing on the expected account."

gcloud compute networks subnets describe "$subnet" --region="$region" "${project[@]}" >/dev/null
instances=$(gcloud compute instances list "${project[@]}" --filter="name=$name" --format=json)
if jq -e 'length > 0' <<< "$instances" >/dev/null; then
  if ! jq -e --arg zone "$zone" --arg subnet "$subnet" '
      length == 1 and (.[0] |
        (.zone | endswith("/" + $zone)) and
        (.machineType | endswith("/e2-micro")) and
        ((.serviceAccounts // []) | length == 0) and
        (.networkInterfaces | length == 1 and all(
          (.subnetwork | endswith("/" + $subnet)) and
          ((.accessConfigs // []) | length == 0) and
          ((.ipv6AccessConfigs // []) | length == 0)
        ))
      )' <<< "$instances" >/dev/null; then
    echo "A VM with this name exists but its configuration differs." >&2
    exit 1
  fi
  disk=$(jq -er '.[0].disks[] | select(.boot) | .source | split("/")[-1]' <<< "$instances")
  boot_disk=$(gcloud compute disks describe "$disk" --zone="$zone" "${project[@]}" --format=json)
  if ! jq -e '(.type | endswith("/pd-standard")) and ((.sizeGb | tonumber) == 30)' \
      <<< "$boot_disk" >/dev/null; then
    echo "The existing VM has an unexpected boot disk configuration." >&2
    exit 1
  fi
  echo "VM $name already exists in $zone with the expected configuration."
  exit 0
fi

if [[ "${PROVISION_MODE:-verify}" == verify ]]; then
  echo "Preflight passed. VM $name is absent."
  exit 0
fi

gcloud compute instances create "$name" "${project[@]}" \
  --zone="$zone" --subnet="$subnet" \
  --machine-type=e2-micro --provisioning-model=STANDARD \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-standard \
  --no-address --no-service-account --no-scopes \
  --metadata=enable-oslogin=TRUE,block-project-ssh-keys=TRUE \
  --labels=app=vpnlens,managed-by=github-actions \
  --format='table(name,zone.basename(),machineType.basename(),status)'
