resource "aws_security_group" "bot_sg_rt" {
  name = "autofutures-rt-sg"
  ingress {
    from_port = 22
    to_port = 22
    protocol = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port = 8080
    to_port = 8081
    protocol = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_instance" "bot_rt" {
  ami = "ami-01811d4912b4ccb26"
  instance_type = var.instance_type
  key_name = var.key_name
  vpc_security_group_ids = [aws_security_group.bot_sg_rt.id]
  root_block_device { volume_size = 20 }
  tags = { Name = "autofutures-rt" }
}
resource "aws_eip" "bot_ip" {
  instance = aws_instance.bot_rt.id
  domain = "vpc"
}
