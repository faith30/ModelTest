// Copyright Epic Games, Inc. All Rights Reserved.

#include "Accolades/LyraAccoladeHostWidget.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(LyraAccoladeHostWidget)

void ULyraAccoladeHostWidget::NativeConstruct()
{
	Super::NativeConstruct();
}

void ULyraAccoladeHostWidget::NativeDestruct()
{
	CancelAsyncLoading();
	Super::NativeDestruct();
}
