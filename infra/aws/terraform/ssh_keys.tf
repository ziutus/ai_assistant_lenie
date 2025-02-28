resource "aws_key_pair" "ziutus_key" {
    key_name = "ziutus_key"
    public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAABJQAAAQEAk+r+zBMhlF0rm4igF8v30QBnySjvFpCWZWGGGbnUrwYPjls1WIU+YWEUcyjfIqp/+UfVRqN47bOz5ZnMPE8JXKQCf3uELliLrTh7C9j/rIcgxn3RLsR3TVrp3JsvylxnPHrlU2F65xOcoSPrkvEJteHsuZkYU/1AlgIdK4EAOfumHjeiJGMA0QuP+zUe2YJ5yU4+CK6A1Ay3jmseNAfRIu/PC5CjxAj4Q8w2sG1yFgbXc7dNM2uCuqftJgvaRrsu/H9ylyT1z031tP2erXb/vQMzOEj3scR7XPcdGkevO/sCK3lIc2aFZAwr47FyNZMSCmmlXFQKzFgp4gOA11us8w== github"
}

resource "aws_key_pair" "lenie_ai_key" {
    key_name = "lenie_ai_key"
    public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILEEUnYKCshJ01MYKaCMXcE53z0VZWIB6qGBS4yCuuHS lenie-default"
}
