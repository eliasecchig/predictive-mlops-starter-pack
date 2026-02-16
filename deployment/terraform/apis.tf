# Enable APIs in the CICD runner project
resource "google_project_service" "cicd_services" {
  count = length(local.cicd_services)

  project            = var.cicd_runner_project_id
  service            = local.cicd_services[count.index]
  disable_on_destroy = false
}

# Enable APIs in the deployment projects (staging and prod)
locals {
  deploy_project_service_pairs = toset([
    for pair in setproduct(keys(local.deploy_project_ids), local.deploy_project_services) :
    "${pair[0]}/${pair[1]}"
  ])
}

resource "google_project_service" "deploy_project_services" {
  for_each = local.deploy_project_service_pairs

  project            = local.deploy_project_ids[split("/", each.key)[0]]
  service            = split("/", each.key)[1]
  disable_on_destroy = false
}
