#!/bin/bash

# Se você não passar nenhuma mensagem, ele usa "Atualização automática"
MENSAGEM=${1:-"Atualização automática"}

echo "Adicionando arquivos..."
git add .

echo "Criando o pacote de envio (commit)..."
git commit -m "$MENSAGEM"

echo "Enviando para o GitHub..."
git push

echo "Pronto! Tudo salvo e enviado."
