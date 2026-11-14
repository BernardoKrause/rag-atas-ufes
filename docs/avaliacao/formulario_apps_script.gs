function criarFormulario() {
  var setores = [
    ['Conselho Departamental do CAR', 'CAR, Goiabeiras', '10 atas, de 02/2025 a 11/2025'],
    ['Conselho Departamental do CCAE', 'CCAE, Alegre', '10 atas, de 01/2025 a 06/2025'],
    ['Departamento DEAL (CCAE)', 'CCAE, Alegre', '20 atas, de 04/2024 a 12/2025'],
    ['Departamento DER (CCAE)', 'CCAE, Alegre', '29 atas, de 02/2024 a 08/2025'],
    ['Departamento DPV (CCAE)', 'CCAE, Alegre', '22 atas, de 03/2024 a 05/2025'],
    ['Conselho Departamental do CCE', 'CCE, Goiabeiras', '69 atas, de 03/2010 a 07/2015'],
    ['Departamento DB (CCENS)', 'CCENS, Alegre', '10 atas, de 05/2024 a 06/2025'],
    ['Departamento DC (CCENS)', 'CCENS, Alegre', '10 atas, de 01/2025 a 07/2025'],
    ['Departamento DFN (CCENS)', 'CCENS, Alegre', '10 atas, de 01/2025 a 06/2025'],
    ['Departamento DG (CCENS)', 'CCENS, Alegre', '10 atas, de 03/2024 a 09/2024'],
    ['Departamento DMPA (CCENS)', 'CCENS, Alegre', '10 atas, de 02/2024 a 08/2024'],
    ['Departamento DQF (CCENS)', 'CCENS, Alegre', '10 atas, de 01/2025 a 06/2025'],
    ['Conselho Departamental do CCHN', 'CCHN, Goiabeiras', '10 atas, de 02/2022 a 04/2023'],
    ['Câmara Local de Graduação do CCHN', 'CCHN, Goiabeiras', '10 atas, de 08/2020 a 07/2021'],
    ['Conselho Departamental do CE', 'CE, Goiabeiras', '10 atas, de 01/2025 a 06/2025'],
    ['Colegiado do Curso de Pedagogia (CE)', 'CE, Goiabeiras', '9 atas, de 05/2003 a 07/2022'],
    ['Conselho Departamental do CEFD', 'CEFD, Goiabeiras', '10 atas, de 02/2023 a 11/2023'],
    ['Conselho Departamental do CEUNES', 'CEUNES, São Mateus', '13 atas, de 01/2024 a 11/2025'],
    ['Departamento DCAB (CEUNES)', 'CEUNES, São Mateus', '12 atas, de 02/2023 a 05/2025'],
    ['Departamento DCE (CEUNES)', 'CEUNES, São Mateus', '15 atas, de 02/2023 a 12/2025'],
    ['Departamento DCN (CEUNES)', 'CEUNES, São Mateus', '6 atas, de 01/2025 a 05/2025'],
    ['Departamento DCS (CEUNES)', 'CEUNES, São Mateus', '6 atas, de 04/2024 a 07/2024'],
    ['Departamento DECH (CEUNES)', 'CEUNES, São Mateus', '6 atas, de 07/2024 a 11/2024'],
    ['Departamento DET (CEUNES)', 'CEUNES, São Mateus', '14 atas, de 01/2023 a 11/2025'],
    ['Departamento DMA (CEUNES)', 'CEUNES, São Mateus', '6 atas, de 01/2025 a 05/2025'],
    ['Conselho Departamental do CT', 'CT, Goiabeiras', '10 atas, de 06/2025 a 12/2025']
  ];

  var form = FormApp.create('Que perguntas você faria sobre as atas do seu setor?');
  form.setDescription(
    'Olá! Sou estudante de Ciência da Computação da UFES e, no meu Trabalho de Conclusão de ' +
    'Curso, desenvolvi um sistema que responde perguntas em linguagem natural sobre atas de ' +
    'reuniões da UFES (câmaras departamentais, conselhos de centro, câmara local e colegiado), ' +
    'sempre indicando de qual ata veio a resposta.\n\n' +
    'Para avaliar o sistema com perguntas reais, quero saber o que você gostaria de perguntar ' +
    'sobre as atas do seu setor. Podem ser coisas que você já precisou procurar ou que seria ' +
    'útil saber.\n\n' +
    '• Leva cerca de 3 minutos.\n' +
    '• A participação é voluntária e anônima: o formulário não coleta nome, e-mail nem ' +
    'qualquer dado que identifique você.\n' +
    '• As perguntas recebidas serão usadas apenas para avaliar o sistema no TCC e podem ' +
    'aparecer no texto do trabalho, sem qualquer identificação.'
  );
  form.setCollectEmail(false);
  form.setLimitOneResponsePerUser(false);
  form.setAllowResponseEdits(false);
  form.setProgressBar(true);
  form.setConfirmationMessage(
    'Obrigado pela contribuição! Suas perguntas vão ajudar a avaliar se o sistema responde ao ' +
    'que as pessoas realmente precisam saber sobre as atas.'
  );

  form.addSectionHeaderItem()
    .setTitle('Atas que o sistema conhece')
    .setHelpText(
      'O sistema conhece somente as atas públicas abaixo. Não são todas as atas de cada setor, ' +
      'apenas as do período indicado.\n\n' +
      setores.map(function (s) { return '• ' + s[0] + ' (' + s[1] + '): ' + s[2]; }).join('\n')
    );

  form.addPageBreakItem().setTitle('Sobre você');
  form.addListItem()
    .setTitle('De qual setor você é?')
    .setChoiceValues(setores.map(function (s) { return s[0]; }).concat(['Outro setor da UFES']))
    .setRequired(true);
  form.addMultipleChoiceItem()
    .setTitle('Qual o seu vínculo?')
    .setChoiceValues([
      'Técnico-administrativo(a)',
      'Docente',
      'Chefia de departamento ou coordenação',
      'Outro'
    ])
    .setRequired(true);

  form.addPageBreakItem()
    .setTitle('Suas perguntas')
    .setHelpText(
      'Escreva perguntas como você faria a uma pessoa que leu todas as atas do seu setor. ' +
      'Alguns exemplos de tipos diferentes:\n' +
      '• "O que o departamento decidiu sobre o pedido de afastamento para doutorado de um ' +
      'professor em 2024?"\n' +
      '• "Quando foi aprovado o novo Projeto Pedagógico do Curso?"\n' +
      '• "Quais departamentos aprovaram a oferta de disciplinas optativas no último semestre?"\n' +
      '• "Como evoluiu a discussão sobre a reforma do laboratório ao longo das reuniões?"\n' +
      '• "O conselho já discutiu a criação de um curso de pós-graduação em X?"\n\n' +
      'Não precisa saber se a resposta existe nas atas.'
    );

  for (var n = 1; n <= 3; n++) {
    form.addParagraphTextItem().setTitle('Pergunta ' + n).setRequired(n === 1);
    form.addTextItem()
      .setTitle('De qual reunião ou período você lembra para a pergunta ' + n + '?')
      .setHelpText('Ex.: "reunião de março de 2024", "algum momento de 2025", "não sei". Opcional.');
    form.addParagraphTextItem()
      .setTitle('Você sabe a resposta da pergunta ' + n + '? Se sim, qual?')
      .setHelpText('Opcional.');
  }

  Logger.log('Link para responder: ' + form.getPublishedUrl());
  Logger.log('Link para editar: ' + form.getEditUrl());
}
