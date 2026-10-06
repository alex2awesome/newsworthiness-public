from transformers import AutoTokenizer
from transformers import DataCollatorForSeq2Seq
from datasets import load_dataset
import evaluate
import numpy as np
from transformers import (
    AutoModelForSeq2SeqLM, Seq2SeqTrainingArguments, Seq2SeqTrainer,
    HfArgumentParser

)
import os
from arguments import ModelArguments, DataTrainingArguments, TrainingArguments
import huggingface_hub
from utils import extend_string_range
huggingface_hub.login(os.environ["HF_TOKEN"])


def compute_metrics(eval_pred):
    predictions, labels = eval_pred
    decoded_preds = tokenizer.batch_decode(predictions, skip_special_tokens=True)
    labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
    decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)
    result = rouge.compute(predictions=decoded_preds, references=decoded_labels, use_stemmer=True)
    prediction_lens = [np.count_nonzero(pred != tokenizer.pad_token_id) for pred in predictions]
    result["gen_len"] = np.mean(prediction_lens)
    return {k: round(v, 4) for k, v in result.items()}


def preprocess_function(examples, max_length):
    prefix = "summarize: "
    inputs = [prefix + doc for doc in examples["text"]]
    model_inputs = tokenizer(inputs, max_length=max_length, truncation=True)
    labels = tokenizer(text_target=examples["summary"])
    model_inputs["labels"] = labels["input_ids"]
    return model_inputs


def freeze_layers(
        model,
        model_name_or_path,
        encoder_layers_to_freeze=None,
        decoder_layers_to_freeze=None,
        layers_to_freeze=None,
):
    if (encoder_layers_to_freeze is not None) or (decoder_layers_to_freeze is not None) or (layers_to_freeze is not None):
        # encoder/decoder architecture
        if 'pegasus' in model_name_or_path or 't5' in model_name_or_path:
            encoder_layers_to_freeze = extend_string_range(encoder_layers_to_freeze)
            decoder_layers_to_freeze = extend_string_range(decoder_layers_to_freeze)
            if 'pegasus' in model_name_or_path:
                encoder_layers = model.model.encoder.layers
                decoder_layers = model.model.decoder.layers
            # t5
            else:
                encoder_layers = model.encoder.block
                decoder_layers = model.decoder.block

            for layer in encoder_layers_to_freeze:
                for p in encoder_layers[layer].parameters():
                    p.requires_grad = False
            for layer in decoder_layers_to_freeze:
                for p in decoder_layers[layer].parameters():
                    p.requires_grad = False

        else:
            raise NotImplementedError('Specific model not supported yet.')



if __name__ == "__main__":
    parser = HfArgumentParser((ModelArguments, DataTrainingArguments, TrainingArguments))
    args = parser.parse_args()

    rouge = evaluate.load("rouge")

    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, cache_dir=args.cache_dir)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model_name_or_path, cache_dir=args.cache_dir)

    freeze_layers(model, args.model_name_or_path, args.encoder_layers_to_freeze, args.decoder_layers_to_freeze)

    dataset = load_dataset(args.dataset_name, split='train')
    tokenized_dataset = dataset.map(preprocess_function, fn_kwargs=dict(max_length=args.max_sequence_length), batched=True)
    tokenized_dataset = tokenized_dataset.train_test_split(test_size=args.train_test_split)
    data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=args.model_name_or_path)

    dataset_name_for_run = args.dataset_name.split('/')[-1].replace('-', '_')
    model_name_for_run = args.model_name_or_path.split('/')[-1].replace('-', '_')
    training_args = Seq2SeqTrainingArguments(
        output_dir=os.path.join(args.output_dir, f'{dataset_name_for_run}__{model_name_for_run}'),
        evaluation_strategy=args.evaluation_strategy,
        save_strategy=args.save_strategy,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.per_device_train_batch_size,
        per_device_eval_batch_size=args.per_device_eval_batch_size,
        weight_decay=args.weight_decay,
        save_total_limit=args.save_total_limit,
        num_train_epochs=args.num_train_epochs,
        predict_with_generate=True,
        fp16=args.fp16,
        push_to_hub=True,
        do_eval=args.do_eval,
        do_train=args.do_train,
        do_predict=args.do_predict,
        overwrite_output_dir=True,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["test"],
        tokenizer=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    trainer.train()
    trainer.push_to_hub()

