import pandas as pd
from transformers import BertTokenizer, AutoModel, AdamW
import torch
from sklearn.model_selection import train_test_split
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler
import torch.nn as nn
import numpy as np
from sklearn.metrics import classification_report

device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
print('GPU state:', device)
PRETRAINED_MODEL_NAME = 'bert-base-uncased'
BATCH_SIZE = 5
EPOCH = 10

bert = AutoModel.from_pretrained(PRETRAINED_MODEL_NAME)
tokenizer = BertTokenizer.from_pretrained(PRETRAINED_MODEL_NAME)


class BERT(nn.Module):
    def __init__(self, bert):
        super(BERT, self).__init__()
        self.bert = bert
        self.dropout = nn.Dropout(0.1)
        self.relu = nn.ReLU()
        # Dense Layer
        self.fc1 = nn.Linear(768, 512)
        self.fc2 = nn.Linear(512, 256)
        self.fc3 = nn.Linear(256, 2)
        self.fc4 = nn.Linear(768, 2)
        self.softmax = nn.LogSoftmax(dim=1)

    def forward(self, sent_id, mask):
        _, cls_hs = self.bert(sent_id, attention_mask=mask)
        # x = self.fc1(cls_hs)
        # x = self.relu(x)
        # x = self.dropout(x)
        # x = self.fc2(x)
        # x = self.relu(x)
        # x = self.dropout(x)
        # #output
        # x = self.fc3(x)
        x = self.fc4(cls_hs)
        x = self.softmax(x)
        return x


def train():
    model.train()
    total_loss, total_accuracy = 0, 0
    total_preds = []

    for step, batch in enumerate(train_dataloader):
        # progress update every 50 batches
        if step%50==0 and not step==0:
            print("Batch {:>5} of {:>5}.".format(step, len(train_dataloader)))
        # push to GPU
        batch = [r.to(device) for r in batch]
        sent_id, mask, labels = batch

        # clear previous gradient
        model.zero_grad()
        # get prediction from current batch
        preds = model(sent_id, mask)
        # calculate loss
        loss = cross_entropy(preds, labels)
        # add to total loss
        total_loss = total_loss + loss.item()
        # backward to calculate gradients
        loss.backward()
        # clip gradient to 1.0 to prevent exploding gradient
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        # update params
        optimizer.step()
        # push back to CPU
        preds=preds.detach().cpu().numpy()

        total_preds.append(preds)
    avg_loss = total_loss/len(train_dataloader)
    total_preds = np.concatenate(total_preds, axis=0)
    return avg_loss, total_preds


def evaluate():
    print("\nEvaluating...")
    model.eval()

    total_loss, total_accuracy = 0, 0
    total_preds = []

    for step, batch in enumerate(val_dataloader):
        if step % 20 == 0 and not step == 0:
            print('  Batch {:>5,}  of  {:>5,}.'.format(step, len(val_dataloader)))
        batch = [t.to(device) for t in batch]
        sent_id, mask, labels = batch

        with torch.no_grad():
            preds = model(sent_id, mask)
            loss = cross_entropy(preds, labels)
            total_loss = total_loss + loss.item()
            preds = preds.detach().cpu().numpy()
            total_preds.append(preds)
    avg_loss = total_loss / len(val_dataloader)
    total_preds = np.concatenate(total_preds, axis=0)
    return avg_loss, total_preds


def tokenize_encode_covert_to_tensor(data, label):
    encode = tokenizer.batch_encode_plus(data.tolist(), max_length=25, pad_to_max_length=True, truncation=True)
    seq = torch.tensor(encode['input_ids'])
    mask = torch.tensor(encode['attention_mask'])
    y = torch.tensor(label.tolist())
    return seq, mask, y


dataset = pd.read_csv('data/Restaurant_Reviews.tsv', delimiter='\t', quoting=3)
dataset['Review'] = dataset['Review'].apply(lambda x: x.lower())

#split data into train, validation and test
train_text, temp_text, train_labels, temp_labels = train_test_split(dataset['Review'], dataset['Liked'],
                                                                    random_state=2018,
                                                                    test_size=0.3,
                                                                    stratify=dataset['Liked'])
val_text, test_text, val_labels, test_labels = train_test_split(temp_text, temp_labels,
                                                                random_state=2018,
                                                                test_size=0.5,
                                                                stratify=temp_labels)

#tokenize and encode sequences, and convert it into tensor
train_seq, train_mask, train_y = tokenize_encode_covert_to_tensor(train_text, train_labels)
test_seq, test_mask, test_y = tokenize_encode_covert_to_tensor(test_text, test_labels)
val_seq, val_mask, val_y = tokenize_encode_covert_to_tensor(val_text, val_labels)

#wrap tensor and sampling data
train_data = TensorDataset(train_seq, train_mask, train_y)
train_sampler = RandomSampler(train_data)
train_dataloader = DataLoader(train_data, sampler=train_sampler, batch_size=BATCH_SIZE)

val_data = TensorDataset(val_seq, val_mask, val_y)
val_sampler = RandomSampler(val_data)
val_dataloader = DataLoader(val_data, sampler=val_sampler, batch_size=BATCH_SIZE)

# prevent bert update params
# for param in bert.parameters():
#     param.requires_grad = False

model = BERT(bert)
model = model.to(device)

optimizer = AdamW(model.parameters(), lr=1e-5)
cross_entropy = nn.CrossEntropyLoss()

best_valid_loss = float('inf')
train_losses = []
valid_losses = []

for epoch in range(EPOCH):
    print("\nEpoch {:} / {:}".format(epoch+1, EPOCH))
    train_loss, _ = train()
    val_loss, _ = evaluate()

    if val_loss < best_valid_loss:
        best_valid_loss = val_loss
        torch.save(model.state_dict(), 'model.pt')
    train_losses.append(train_loss)
    valid_losses.append(val_loss)
    print(f"\nTraining Loss: {train_loss:.3f}")
    print(f"Validation Loss: {best_valid_loss:.3f}")

path = 'model.pt'
model.load_state_dict(torch.load(path))

with torch.no_grad():
    preds = model(test_seq.to(device), test_mask.to(device))
    preds = preds.detach().cpu().numpy()

preds = np.argmax(preds, axis=1)
print(classification_report(test_y, preds))
for i in range(10):
    print(test_text.tolist()[i], test_y.tolist()[i], preds[i])