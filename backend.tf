terraform {
  backend "s3" {
    bucket         = "terraform-state-919421378820"
    key            = "lab/terraform.tfstate"
    region         = "ap-southeast-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}